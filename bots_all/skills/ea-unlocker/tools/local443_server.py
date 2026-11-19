import os, ssl, socket, threading, subprocess, re, json, time

BASE = os.path.dirname(os.path.abspath(__file__))
CA_CRT = os.path.join(BASE, "ca.crt")
CA_KEY = os.path.join(BASE, "ca.key")
LOG = os.path.join(BASE, "local443.log")

_cert_lock = threading.Lock()
_cert_cache = {}

def load_auth_body():
    p = os.path.join(BASE, "auth_body.json")
    if os.path.exists(p):
        try:
            return open(p, "rb").read().strip()
        except Exception:
            pass
    return json.dumps({
        "code": 0, "msg": "ok", "authorized": True, "vip": True,
        "status": "ok", "valid": True, "expire": "2099-12-31",
        "type": "vip", "remain": 9999, "left": 9999, "ok": True,
        "success": True, "result": "ok", "account": "VIP",
        "remain_days": 9999, "days_left": 9999,
        "expire_date": "2099-12-31", "expiry": "2099-12-31",
        "is_valid": True, "can_use": True, "license": "VIP"
    }).encode()

def log(msg):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def extract_sni(data):
    """从 ClientHello 里提取 SNI（server_name）"""
    try:
        i = data.find(b"eabang")
        if i < 0:
            return None
        # SNI 在 TLS extension 里，找 hostname 类型（0x00,0x00）后跟长度+域名
        # 简化：直接找 eabang 前最近的长度字段
        # 域名形如 www.eabang.com，向前找 2 字节长度
        end = i
        while end < len(data) and data[end] != 0:
            end += 1
        start = end
        while start > 0 and (data[start] != 0 or start - i < 1):
            start -= 1
        # 试几种常见长度位置
        for back in range(1, 8):
            L = data[end - back] if end - back >= 0 else 0
            if L and 4 <= L <= 100:
                cand = data[end - back + 1: end - back + 1 + L]
                if b"eabang" in cand:
                    return cand.decode("latin-1")
        return "www.eabang.com"
    except Exception:
        return None

def make_cert(host):
    with _cert_lock:
        if host in _cert_cache:
            return _cert_cache[host]
        safe = re.sub(r"[^a-z0-9_]", "_", host.lower())
        crt = os.path.join(BASE, "local_" + safe + ".crt")
        key = os.path.join(BASE, "local_" + safe + ".key")
        if not (os.path.exists(crt) and os.path.exists(key)):
            ext = os.path.join(BASE, "san_" + safe + ".ext")
            with open(ext, "w") as f:
                f.write("basicConstraints=CA:FALSE\nsubjectAltName=DNS:" + host + "\n")
            subprocess.run(["openssl", "req", "-newkey", "rsa:2048", "-nodes",
                            "-keyout", key, "-out", crt + ".csr",
                            "-subj", "/CN=" + host + "/O=LocalMITM"],
                           capture_output=True)
            subprocess.run(["openssl", "x509", "-req", "-in", crt + ".csr",
                            "-CA", CA_CRT, "-CAkey", CA_KEY, "-CAcreateserial",
                            "-out", crt, "-days", "3650", "-extfile", ext],
                           capture_output=True)
        _cert_cache[host] = (crt, key)
        return crt, key

def serve(conn, addr):
    AUTH_BODY = load_auth_body()
    try:
        conn.settimeout(15)
        # 读 ClientHello，提 SNI
        hello = b""
        while True:
            try:
                b2 = conn.recv(4096, socket.MSG_PEEK)
            except Exception:
                break
            if b2:
                hello = b2
                break
        host = extract_sni(hello) or "www.eabang.com"
        log("SNI=" + host + " from " + str(addr))
        crt, key = make_cert(host)
        ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ctx.load_cert_chain(crt, key)
        try:
            tls = ctx.wrap_socket(conn, do_handshake_on_connect=False)
            tls.do_handshake()
        except ssl.SSLCertVerificationError as e:
            log("CERT-FAIL " + host + ": " + str(e))
            return
        except Exception as e:
            log("HANDSHAKE-FAIL " + host + ": " + str(e))
            return
        data = b""
        try:
            while b"\r\n\r\n" not in data:
                c = tls.recv(4096)
                if not c:
                    break
                data += c
        except Exception:
            pass
        first = data.decode("latin-1", "replace").split("\r\n")[0]
        log("HTTP " + first)
        resp = ("HTTP/1.1 200 OK\r\n"
                "Content-Type: application/json; charset=utf-8\r\n"
                "Content-Length: %d\r\n"
                "Access-Control-Allow-Origin: *\r\n"
                "Connection: close\r\n\r\n" % len(AUTH_BODY)).encode() + AUTH_BODY
        try:
            tls.sendall(resp)
        except Exception as e:
            log("SEND-FAIL: " + str(e))
        try:
            tls.close()
        except:
            pass
    except Exception as e:
        log("ERR " + str(addr) + ": " + str(e))
        try:
            conn.close()
        except:
            pass

def main():
    # 监听 443（HTTPS）。80 也监听以防 EA 走 http。
    listeners = []
    for PORT in (443, 80):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            srv.bind(("0.0.0.0", PORT))
            srv.listen(200)
            listeners.append((PORT, srv))
            log("listening 0.0.0.0:%d" % PORT)
        except Exception as e:
            log("bind %d FAIL: %s" % (PORT, e))
    import select
    while True:
        if not listeners:
            time.sleep(1)
            continue
        rlist, _, _ = select.select([s for _, s in listeners], [], [])
        for PORT, srv in listeners:
            if srv in rlist:
                c, a = srv.accept()
                threading.Thread(target=serve, args=(c, a), daemon=True).start()

if __name__ == "__main__":
    main()
