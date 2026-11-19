#!/usr/bin/env python3
"""
scan_locks.py - EA 锁型 30 秒诊断（本岗 §1 SOP 的脚本化）
用法: python scan_locks.py <ex5/ex4 文件路径>
输出: 锁型判断 + 厂商域名 + 建议打法
不修改原文件，纯只读。
"""
import sys, re, struct, json

def find_all(pat, buf):
    off, res = 0, []
    while True:
        i = buf.find(pat, off)
        if i < 0: break
        res.append(i)
        off = i + 1
    return res

def main(path):
    data = open(path, "rb").read()
    print(f"文件: {path}  大小: {len(data)} 字节")

    # 1. 魔数判定
    magic = data[:4]
    if magic == b"EX5\x02":
        ver = "EX5v2 (MT5)"
    elif magic == b"EX4\x02":
        ver = "EX4v2 (MT4)"
    elif magic == b"\x4a\x43\x04\x00":
        ver = "EX5/EX4 旧版 (MetaQuotes 早期)"
    else:
        ver = "未知/非 MT 编译体"
    print(f"魔数: {ver}")

    # 2. 厂商域名 / URL 扫描（ASCII + UTF-16LE）
    doms = set()
    for m in re.finditer(rb"https?://([a-zA-Z0-9\.\-]+)", data):
        doms.add(m.group(1).decode())
    for m in re.finditer(rb"(?:[\x20-\x7e]\x00)*([a-zA-Z0-9\-]+\.(?:com|cn|net|org|io|cc)\x00)", data):
        doms.add(m.group(1).decode().replace("\x00",""))
    doms = {d for d in doms if len(d) > 4 and "metaquotes" not in d.lower()}
    print(f"厂商域名/URL: {sorted(doms) if doms else '无明文（在线锁证据弱/无）'}")

    # 3. 在线锁指纹
    online_signals = []
    for s in [b"WebRequest", b"SocketCreate", b"SocketConnect", b"http", b"https"]:
        if find_all(s, data):
            online_signals.append(s.decode("latin-1"))
        if find_all(s.decode("latin-1").encode("utf-16-le"), data):
            online_signals.append(s.decode("latin-1") + "(UTF16)")
    online_signals = sorted(set(online_signals))
    print(f"在线锁指纹: {online_signals if online_signals else '弱'}")

    # 4. 时间锁指纹（明文时间戳候选）
    ts_hits = []
    for off in range(0, len(data)-4, 4):
        v = struct.unpack_from("<I", data, off)[0]
        if 1_500_000_000 <= v <= 2_100_000_000:
            ts_hits.append((off, v))
    # 噪声过滤: 真时间锁只有 1-3 处有意义时间戳; >50 处=随机字节噪声不算证据
    ts_meaningful = ts_hits if len(ts_hits) <= 50 else []
    print(f"unix时间戳候选: {len(ts_hits)} 处 {('<- 噪声, 不算时间锁证据' if len(ts_hits)>50 else '')}")

    # 5. 高熵密文特征（代码段是否加密）
    import math
    code = data[0x3a8:] if len(data) > 0x3a8 else data[1024:]
    zeros = code.count(0)
    entropy = -sum((code.count(b)/len(code))*math.log2(code.count(b)/len(code)) for b in set(code) if code.count(b))
    print(f"代码段(0x3a8+) 零字节密度: {zeros*100//len(code)}%  熵: {entropy:.2f} (≈8=高熵密文/加密, <5=明文)")

    # 6. 综合判断
    print("\n=== 锁型判断 ===")
    has_http = "http" in online_signals or "https" in online_signals
    if has_http and len(doms) > 0:
        print("→ 在线验证锁（厂商域名 + http(s) 指纹）")
        print("→ 打法: §3 本地 MITM 劫持")
    elif has_http:
        print("→ 在线锁嫌疑（有 http(s) 指纹, 但域名没扫到明文, 可能被混淆）")
        print("→ 打法: §3 本地 MITM 劫持 (拦所有可疑域名)")
    elif ts_meaningful:
        print("→ 本地时间锁嫌疑 (少量有意义时间戳)")
        print("→ 打法: 先改系统时钟续命; 要治本需反汇编(工具有限)")
    else:
        print("→ 指纹不明 (高熵密文, 明文特征被混淆), 需挂 EA 看实际行为判")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    main(sys.argv[1])
