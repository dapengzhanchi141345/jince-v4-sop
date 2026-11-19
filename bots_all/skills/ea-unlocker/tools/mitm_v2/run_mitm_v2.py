#!/usr/bin/env python
"""MITM v2 通用代理 —— 在线验证锁核心武器
监听 127.0.0.1:8888, 拦截 CONNECT 厂商域名, 当场伪造证书 + 回「已授权」响应。
非拦截域名 502 丢弃(保证只有验证请求被劫持, 不碰交易流量)。
用法: python run_mitm_v2.py   (先改 config.py; 先跑 gen_ca.py; 再 import_ca.bat)
验证: curl --cacert ca/ca.crt -x http://127.0.0.1:8888 https://www.<厂商>/
"""
import os, ssl, socket, threading, subprocess, re, json, time, sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import config

PORT = 8888
CA_CRT = os.path.join(BASE, "ca", "ca.crt")
CA_KEY = os.path.join(BASE, "ca", "ca.key")
LOG = os.path.join(BASE, "traffic.log")

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
    # 缺省全字段兜底体: authorized/vip/expire/valid/remain/success/code 全塞, 提高命中
    return json.dumps({
        "code": 0, "msg": "ok", "authorized": True, "vip": True,
        "status": "ok", "valid": True, "expire": "2099-12-31",
        "type": "vip", "remain": 9999, "left": 9999, "ok": True,
        "success": True, "result": "ok", "authorized_count": 99,
        "account": "VIP", "remain_days": 9999, "days_left": 9999,
        "expire_date": "2099-12-31", "expiry": "2099-12-31",
        "is_valid": True, "can_use": True, "license": "VIP"
    }).encode()

_cert_cache = {}
_cert_lock = threading.Lock()

def get_forged_cert(host):
    """按 SNI/CONNECT 域名, 用本地 CA 签一张该域名的证书(缓存到磁盘)"""
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
            r = subprocess.run(["openssl", "x509", "-req", "-in", crt + ".csr",
                                "-CA", CA_CRT, "-CAkey", CA_KEY, "-CAcreateserial",
                                "-out", crt, "-days", "3650", "-extfile", ext],
                               capture_output=True)
            if r.returncode != 0:
                log("FORGED-CERT-FAIL " + host + ": " + r.stderr.decode()[:200])
        _cert_cache[host] = (crt, key)
        return crt, key

def read_http_head(tls, data=b"", with_content_length=False):
    while b"\r\n\r\n" not in data:
        chunk = tls.recv(4096)
        if not chunk:
            break
        data += chunk
    if with_content_length:
        m = re.search(rb"Content-Length:\s*(\d+)", data, re.I)
        if m:
            need = int(m.group(1))
            he = data.find(b"\r\n\r\n")
            have = len(data) - he - 4
            while have < need:
                c2 = tls.recv(4096)
                if not c2:
                    break
                data += c2
                have = len(data) - he - 4
    return data

def handle_tls(client, host):
    body = load_auth_body()  # 每请求重读, 支持热切换伪造体
    ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    crt, key = get_forged_cert(host)
    ctx.load_cert_chain(crt, key)
    try:
        tls = ctx.wrap_socket(client, server_side=True)
    except Exception as e:
        log("TLS-FAIL %s: %s" % (host, e))
        return
    try:
        data = read_http_head(tls, with_content_length=True)
        first = data.decode("latin-1", "replace").split("\r\n")[0]
        log("INTERCEPT %s %s" % (host, first))
        log("REQ-HEAD: " + data.decode("latin-1", "replace")[:400].replace("\r\n", " | "))
        resp = ("HTTP/1.1 200 OK\r\n"
                "Content-Type: application/json; charset=utf-8\r\n"
                "Content-Length: %d\r\n"
                "Access-Control-Allow-Origin: *\r\n"
                "Connection: close\r\n\r\n" % len(body)).encode() + body
        tls.sendall(resp)
    except Exception as e:
        log("SEND-FAIL %s: %s" % (host, e))
    try:
        tls.close()
    except Exception:
        pass

def handle(client, addr):
    try:
        data = b""
        client.settimeout(10)
        while b"\r\n\r\n" not in data:
            c = client.recv(4096)
            if not c:
                break
            data += c
        line = data.decode("latin-1", "replace").split("\r\n")[0]
        log("REQ: " + line[:200])
        m = re.match(r"CONNECT\s+([^\s:]+):\d+", line)
        if m:
            host = m.group(1)
            if config.vendor_substr in host.lower():
                log("INTERCEPT-CONNECT %s" % host)
                client.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
                handle_tls(client, host)
            else:
                log("DROP-CONNECT %s (非拦截域)" % host)
                client.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
        else:
            # 明文 HTTP 直连(非 CONNECT)
            if config.vendor_substr in line.lower() or config.vendor_substr in data.decode("latin-1", "replace").lower():
                body = load_auth_body()
                log("INTERCEPT-HTTP: " + line)
                client.sendall(("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                                 "Content-Length: %d\r\n\r\n" % len(body)).encode() + body)
            else:
                log("DROP-HTTP: " + line[:120])
                client.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
    except Exception as e:
        log("ERR %s: %s" % (addr, e))
    finally:
        try:
            client.close()
        except Exception:
            pass

def main():
    if not (os.path.exists(CA_CRT) and os.path.exists(CA_KEY)):
        print("先跑 gen_ca.py 生成 CA!")
        sys.exit(1)
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", PORT))
    srv.listen(100)
    log("=== MITM v2 @127.0.0.1:%d vendor=%r ===" % (PORT, config.vendor_substr))
    log("验证: curl --cacert %s -x http://127.0.0.1:%d https://%s/" % (CA_CRT, PORT, config.default_sni))
    while True:
        c, a = srv.accept()
        threading.Thread(target=handle, args=(c, a), daemon=True).start()

if __name__ == "__main__":
    main()
