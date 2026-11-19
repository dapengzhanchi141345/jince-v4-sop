#!/usr/bin/env python
"""EX4/EX5 锁型诊断扫描器 v2
用法:
  python exscan.py  <ex5/ex4 路径> [vendor_hint 厂商域名提示]
输出:
  - ASCII/UTF-16 串指纹（域名、http、提示语）
  - 32 位时间戳候选（20xx 年过滤，>1 处才报）
  - 头部指纹区（0x00-0x60 hex dump）
  - 代码段熵（判断是否加密/混淆）
  - 锁型初判: 在线验证 / 本地时间锁 / 账户绑定 / 未知
判完锁型再选路: 在线锁->tools/mitm_v2  |  本地时间锁->clock_shift.py  |  打不动->诚实收尾
"""
import sys, os, re, struct, math, json

VENDOR_HINT = ""  # 由 main 填

def shannon(data: bytes) -> float:
    if not data:
        return 0.0
    freq = {}
    for b in data:
        freq[b] = freq.get(b, 0) + 1
    n = len(data)
    return -sum((c / n) * math.log2(c / n) for c in freq.values())

def find_strings(data: bytes, min_len=4):
    """ASCII + UTF-16LE 串提取（EX5 字符串常以 UTF-16LE 存放）"""
    out = set()
    for m in re.finditer(rb"[\x20-\x7e]{%d,}" % min_len, data):
        s = m.group().decode("latin-1")
        out.add(s)
    # UTF-16LE
    for m in re.finditer(rb"(?:[\x00-\x7f][\x00]){%d,}" % min_len, data):
        try:
            s = m.group().decode("utf-16-le")
            s = s.strip("\x00 ")
            if len(s) >= min_len:
                out.add(s)
        except Exception:
            pass
    return out

def find_dates(data: bytes):
    """找 32 位 unix 时间戳候选（2000-02.09 ~ 2099.01.01，秒级）"""
    out = []
    for i in range(0, len(data) - 4):
        v = struct.unpack_from("<I", data, i)[0]
        if 946684800 <= v <= 4102444800:
            out.append((i, v))
        v2 = struct.unpack_from(">I", data, i)[0]
        if 946684800 <= v2 <= 4102444800 and v2 != v:
            out.append((i, v2))
    return out

def date_human(ts: int) -> str:
    import datetime
    return datetime.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M")

def main():
    global VENDOR_HINT
    if len(sys.argv) < 2:
        print(__doc__)
        return
    path = sys.argv[1]
    VENDOR_HINT = sys.argv[2].lower() if len(sys.argv) > 2 else ""
    data = open(path, "rb").read()
    print("=" * 60)
    print("文件: %s  大小: %d bytes" % (os.path.basename(path), len(data)))
    head = data[:16].hex()
    print("头部16B hex: " + head)
    magic = head[:4]
    if magic == "4d543530":  # MT5\0
        print("格式: MT5 (EX5) — 现代加密混淆格式")
    elif magic in ("4d543430",):  # MT4\0
        print("格式: MT4 (EX4) — 旧格式，部分块可解密")
    else:
        print("格式: 未知头部 %s（可能非原生 MT 文件 / 带壳）" % magic)

    # --- 熵：整体 + 分段 ---
    third = len(data) // 3
    ent = [shannon(data[:third]), shannon(data[third:2*third]), shannon(data[2*third:])]
    ent_all = shannon(data)
    print("熵: 整=%.3f  前三段=%s  (≈8.0 = 密文/压缩, <5 = 有明文区)" % (ent_all, ["%.2f" % e for e in ent]))
    encrypted = ent_all > 7.0

    strs = sorted(find_strings(data))
    print("\n--- 串指纹 (%d 条, 展示前 60 条) ---" % len(strs))
    pat = re.compile(r"https?://|\.com|\.cn|\.net|\.org|\.cc|\.info|\.xyz|www\.|api", re.I)
    interesting = [s for s in strs if pat.search(s)]
    for s in interesting[:60]:
        mark = "  [VENDOR]" if VENDOR_HINT and VENDOR_HINT in s.lower() else ""
        print("  " + s + mark)
    if not interesting:
        print("  (无域名/网络相关串 → 倾向本地锁)")

    # 时间戳
    hits = find_dates(data)
    if hits:
        from collections import Counter
        c = Counter(v for _, v in hits)
        top = c.most_common(5)
        print("\n--- 时间戳候选: 共 %d 处, 高频 TOP5 ---" % len(hits))
        for v, n in top:
            if n >= 2:
                print("  0x%08x = %s  x%d" % (v, date_human(v), n))
        if not any(n >= 2 for _, n in top):
            print("  (均为孤点, 疑噪声, 需结合现象判断)")

    # 厂商提示语
    print("\n--- 可疑提示语（到期/授权/账号）---")
    tip_pat = re.compile(r"到期|过期|未授权|试用|授权|VIP|license|expir|trial|valid|activ|账号|绑定", re.I)
    tips = [s for s in strs if tip_pat.search(s) and len(s) < 200]
    for s in tips[:20]:
        print("  " + s)

    # --- 初判 ---
    print("\n=== 锁型初判 ===")
    verdict = []
    has_net = bool(interesting)
    if has_net:
        verdict.append("有网络/域名串 → 大概率【在线验证锁】→ 走 MITM v2 (tools/mitm_v2/run_mitm_v2.py)")
    ts_signal = [v for v in c.most_common(3) if v[1] >= 2] if hits else []
    if ts_signal:
        verdict.append("有多处重复时间戳 → 疑似【本地时间锁】→ 先试 tools/clock_shift.py 改时钟续命")
    if not has_net and not ts_signal:
        verdict.append("无网络串、无明确时间戳 → 可能: 加密隐藏了网络串 / 账户绑定 / 文件外置加密")
        verdict.append("→ 补问用户到期现象再定; 也可先跑 MITM 观察 EA 到底请求什么域名")
    for v in verdict:
        print("  * " + v)
    print("\n建议顺序: 1)问用户到期现象  2)按上面试路  3)打不动→代做/续费两条路")

if __name__ == "__main__":
    main()
