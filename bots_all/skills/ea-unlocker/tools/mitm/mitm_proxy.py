import os, ssl, socket, threading, subprocess, re, json, time

HOST = "127.0.0.1"
PORT = 8888
BASE = os.path.dirname(os.path.abspath(__file__))
CA_CRT = os.path.join(BASE, "ca.crt")
CA_KEY = os.path.join(BASE, "ca.key")
LOG = os.path.join(BASE, "traffic.log")
INTERCEPT_SUBSTR = "eabang"

def load_auth_body():
    p = os.path.join(BASE, "auth_body.json")
    if os.path.exists(p):
        try:
            with open(p, "rb") as f:
                return f.read().strip()
        except Exception:
            pass
    return json.dumps({
        "code": 0, "msg": "ok", "authorized": True, "vip": True,
        "status": "ok", "valid": True, "expire": "2099-12-31",
        "type": "vip", "remain": 9999, "left": 9999, "ok": True,
        "success": True, "result": "ok", "authorized_count": 99,
        "account": "VIP", "remain_days": 9999, "days_left": 9999,
        "expire_date": "2099-12-31", "expiry": "2099-12-31"
    }).encode()

AUTH_BODY = load_auth_body()

def log(msg):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")

_cert_cache = {}

def get_forged_cert(server_host):
    if server_host in _cert_cache:
        return _cert_cache[server_host]
    safe = server_host.replace(".", "_")
    crt = os.path.join(BASE, "server_" + safe + ".crt")
    key = os.path.join(BASE, "server_" + safe + ".key")
    ext = os.path.join(BASE, "san.ext")
    with open(ext, "w") as f:
        f.write("basicConstraints=CA:FALSE\nsubjectAltName=DNS:" + server_host + "\n")
    subprocess.run(["openssl", "req", "-newkey", "rsa:2048", "-nodes",
                    "-keyout", key, "-out", crt + ".csr",
                    "-subj", "/CN=" + server_host + "/O=LocalMITM"],
                   capture_output=True)
    r = subprocess.run(["openssl", "x509", "-req", "-in", crt + ".csr",
                        "-CA", CA_CRT, "-CAkey", CA_KEY, "-CAcreateserial",
                        "-out", crt, "-days", "3650", "-extfile", ext],
                       capture_output=True)
    if r.returncode != 0:
        log("FORGED-CERT-FAIL " + server_host + ": " + r.stderr.decode())
    _cert_cache[server_host] = (crt, key)
    return crt, key

def handle_tls(client_sock, server_host):
    global AUTH_BODY
    AUTH_BODY = load_auth_body()   # 每次请求重读，方便热切换
    ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    crt, key = get_forged_cert(server_host)
    ctx.load_cert_chain(crt, key)
    try:
        tls = ctx.wrap_socket(client_sock, server_side=True)
    except Exception as e:
        log("TLS-FAIL %s: %s" % (server_host, e))
        return
    data = b""
    try:
        while b"\r\n\r\n" not in data:
            chunk = tls.recv(4096)
            if not chunk:
                break
            data += chunk
        # 继续读 body（如果有）
        m = re.search(rb"Content-Length:\s*(\d+)", data, re.I)
        if m:
            need = int(m.group(1))
            header_end = data.find(b"\r\n\r\n")
            body_len = len(data) - header_end - 4
            while body_len < need:
                c2 = tls.recv(4096)
                if not c2:
                    break
                data += c2
                body_len = len(data) - header_end - 4
    except Exception:
        pass
    req = data.decode("latin-1", "replace")
    first = req.split("\r\n")[0]
    log("HTTPS %s -> %s" % (server_host, first))
    log("REQ-HEAD: %s" % req[:400])
    resp = ("HTTP/1.1 200 OK\r\n"
            "Content-Type: application/json; charset=utf-8\r\n"
            "Content-Length: %d\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "Connection: close\r\n\r\n" % len(AUTH_BODY)).encode() + AUTH_BODY
    try:
        tls.sendall(resp)
    except Exception as e:
        log("SEND-FAIL %s: %s" % (server_host, e))
    try:
        tls.close()
    except:
        pass

def handle(client, addr):
    try:
        data = b""
        while b"\r\n\r\n" not in data:
            c = client.recv(4096)
            if not c:
                break
            data += c
        line = data.decode("latin-1", "replace").split("\r\n")[0]
        log("REQ: " + line)
        m = re.match(r"CONNECT\s+([^\s:]+):(\d+)", line)
        if m:
            host, port = m.group(1), int(m.group(2))
            if INTERCEPT_SUBSTR in host.lower():
                log("INTERCEPT %s:%d -> forged authorized" % (host, port))
                client.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
                handle_tls(client, host)
            else:
                log("PASS-THROUGH %s:%d (non-intercept)" % (host, port))
                client.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
        else:
            if INTERCEPT_SUBSTR in line.lower():
                log("INTERCEPT-HTTP: " + line)
                AUTH_BODY = load_auth_body()
                resp = ("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                        "Content-Length: %d\r\n\r\n" % len(AUTH_BODY)).encode() + AUTH_BODY
                client.sendall(resp)
            else:
                log("502 non-intercept HTTP: " + line)
                client.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
        client.close()
    except Exception as e:
        log("HANDLE-ERR %s: %s" % (addr, e))
        try:
            client.close()
        except:
            pass

def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen(100)
    log("MITM proxy listening on %s:%d" % (HOST, PORT))
    while True:
        c, a = srv.accept()
        threading.Thread(target=handle, args=(c, a), daemon=True).start()

if __name__ == "__main__":
    main()
