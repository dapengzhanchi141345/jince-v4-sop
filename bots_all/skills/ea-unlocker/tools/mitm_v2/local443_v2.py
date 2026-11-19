#!/usr/bin/env python
"""本地 443/80 伪造服务 —— DNS/hosts 劫持路线用(配合改 hosts + 系统根CA)
与 mitm_proxy 不同: 不走代理, 直接监听 443/80, 从 ClientHello 提 SNI, 当场签证书回伪造体。
需要管理员(占 443/80)。非管理员场景优先用 mitm v2 代理路线。
用法: python local443_v2.py  (先改 config.py)
"""
import os, ssl, socket, threading, subprocess, re, json, time, sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import config

CA_CRT = os.path.join(BASE, "ca", "ca.crt")
CA_KEY = os.path.join(BASE, "ca", "ca.key")
LOG = os.path.join(BASE, "local443.log")
_cert_cache = {}
_cert_lock = threading.Lock()

def log(msg):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def load_auth_body():
    p = config.auth_body_file
    if not os.path.isabs(p):
        p = os.path.join(BASE, p)
    if os.path.exists(p):
        try:
            return open(p, "rb").read().strip()
        except Exception:
            pass
    return json.dumps({
        "code": 0, "msg": "ok", "authorized": True, "vip": True, "status": "ok",
        "valid": True, "expire": "2099-12-31", "type": "vip", "remain": 9999,
        "left": 9999, "ok": True, "success": True, "result": "ok",
        "account": "VIP", "remain_days": 9999, "days_left": 9999,
        "expire_date": "2099-12-31", "expiry": "2099-12-31"
    }).encode()

def extract_sni(data: bytes):
    """通用 SNI 提取: 在 ClientHello 里找 server_name 扩展(0x00), 解析 2B 总长+2B 名长+域名"""
    try:
        i = data.find(b"\x00\x00")  # 粗略定位
        # 更可靠: 找扩展类型 0x00(后跟 2B 长度, 再 2B 服务器名长度, 再域名)
        pos = 0
        while pos < len(data) - 6:
            ext_type = struct_unpack_u16(data, pos)
            if ext_type == 0:  # server_name
                ext_len = struct_unpack_u16(data, pos + 2)
                name_len = struct_unpack_u16(data, pos + 4)
                host = data[pos + 6: pos + 6 + name_len].decode("latin-1")
                if host and all(32 <= ord(c) < 127 for c in host):
                    return host
            pos += 1
    except Exception:
        pass
    return None

def struct_unpack_u16(d, i):
    return (d[i] << 8) | d[i + 1]

def make_cert(host):
    with _cert_lock:
        if host in _cert_cache:
            return _cert_cache[host]
        safe = re.sub(r"[^a-z0-9_]", "_", host.lower())
        crt = os.path.join(BASE, "crt", safe + ".crt")
        key = os.path.join(BASE, "crt", safe + ".key")
        os.makedirs(os.path.dirname(crt), exist_ok=True)
        if not (os.path.exists(crt) and os.path.exists(key)):
            ext = os.path.join(BASE, "crt", safe + ".ext")
            with open(ext, "w") as f:
                f.write("basicConstraints=CA:FALSE\nsubjectAltName=DNS:" + host + "\n")
            subprocess.run(["openssl", "req", "-newkey", "rsa:2048", "-nodes",
                            "-keyout", key, "-out", crt + ".csr",
                            "-subj", "/CN=" + host + "/O=LocalMITM"], capture_output=True)
            subprocess.run(["openssl", "x509", "-req", "-in", crt + ".csr",
                            "-CA", CA_CRT, "-CAkey", CA_KEY, "-CAcreateserial",
                            "-out", crt, "-days", "3650", "-extfile", ext], capture_output=True)
        _cert_cache[host] = (crt, key)
        return crt, key

def serve(conn, addr):
    body = load_auth_body()
    try:
        conn.settimeout(15)
        try:
            hello = conn.recv(4096, socket.MSG_PEEK)
        except Exception:
            return
        host = extract_sni(hello)
        if not host:
            for cand in getattr(config, "extra_sans", []) or [config.default_sni]:
                if cand.encode() in hello:
                    host = cand
                    break
        host = host or config.default_sni
        log("SNI=" + host)
        ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ctx.load_cert_chain(*make_cert(host))
        try:
            tls = ctx.wrap_socket(conn, do_handshake_on_connect=False)
            tls.do_handshake()
        except Exception as e:
            log("HANDSHAKE-FAIL %s: %s" % (host, e))
            return
        data = b""
        while b"\r\n\r\n" not in data:
            c = tls.recv(4096)
            if not c:
                break
            data += c
        log("HTTP " + data.decode("latin-1", "replace").split("\r\n")[0])
        tls.sendall(("HTTP/1.1 200 OK\r\nContent-Type: application/json; charset=utf-8\r\n"
                     "Content-Length: %d\r\nAccess-Control-Allow-Origin: *\r\n"
                     "Connection: close\r\n\r\n" % len(body)).encode() + body)
        tls.close()
    except Exception as e:
        log("ERR %s: %s" % (addr, e))

def main():
    listeners = []
    for PORT in (443, 80):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("0.0.0.0", PORT))
            s.listen(200)
            listeners.append((PORT, s))
            log("listening 0.0.0.0:%d" % PORT)
        except Exception as e:
            log("bind %d FAIL: %s" % (PORT, e))
    if not listeners:
        log("无可用端口(443/80 被占?) — 查 netstat, 别擅自杀进程")
        return
    import select
    while True:
        rlist, _, _ = select.select([s for _, s in listeners], [], [])
        for PORT, srv in listeners:
            if srv in rlist:
                c, a = srv.accept()
                threading.Thread(target=serve, args=(c, a), daemon=True).start()

if __name__ == "__main__":
    main()
