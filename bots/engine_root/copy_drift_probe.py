# -*- coding: utf-8 -*-
"""双树副本漂移探针 (0 LLM, chief 07:53 治本批): 同名文件散多处, 只改一份就漂移(07:06 误读根因).
live job 真跑副本 = E:/workbuddy/国外模型/hermes/scripts/. 其余副本关键逻辑不一致 -> exit 1 + 点名漂移文件,
供 no_agent / 段报拾取. 治标=各副本全补 rc==3+TIMECAP(已做); 治本=本探针每开评跑一遍, 漂移即报警.
单一副本收敛(删软链)列 rd_queue 后续, 全路径清点后再动.
判定用"关键逻辑行"指纹(容忍注释/whitespace), 比整文件 md5 稳: 只盯实质逻辑漂移(rc==3 让位 / TIMECAP 下沉)."""
import os, sys, hashlib

# 每组 = 本应内容一致的同名副本. live 那份是 01:30/00:10 job 真跑的, 其余是旧树.
GROUPS = [
    ("training_full_universe.py", [
        r"E:/workbuddy/国外模型/hermes/scripts/training_full_universe.py",  # live
        r"E:/GoldstrategyEngine/training_full_universe.py",
        r"C:/Users/ASUS/jince-engine/training_full_universe.py",
    ]),
    ("backtest_engine.py", [
        r"E:/GoldstrategyEngine/backtest_engine.py",
        r"C:/Users/ASUS/jince-engine/backtest_engine.py",
    ]),
]
# 每组盯的"关键逻辑标记"(整组都须含; 缺 = 实质漂移, 谁只改了一份)
REQUIRED_MARKERS = {
    "training_full_universe.py": ["rc == 3"],
    "backtest_engine.py": ["300s 限时"],
}


def fingerprint(path, name):
    """读文件, 摘出关键逻辑行拼成指纹. 读不到/缺标记返回对应特殊串, 正常返回关键行本体."""
    if not os.path.exists(path):
        return "ABSENT"
    try:
        txt = open(path, encoding="utf-8", errors="replace").read()
    except Exception:
        return "READ_FAIL"
    markers = REQUIRED_MARKERS.get(name, [])
    hit = [ln.strip() for ln in txt.splitlines() if any(m in ln for m in markers)]
    if markers:
        if hit:
            return "\n".join(hit)  # 关键逻辑行本体当指纹(容忍注释/whitespace 差异)
        h = hashlib.md5(txt.encode("utf-8", "replace")).hexdigest()[:8]
        return "MISSING_MARKERS_%s" % h
    return "NO_MARKER_NA"


def main():
    drift = []
    for name, paths in GROUPS:
        fps = {p: fingerprint(p, name) for p in paths}
        for p, fp in fps.items():
            if fp == "ABSENT":
                drift.append("MISSING_FILE %s @ %s" % (name, p))
            elif fp == "READ_FAIL" or str(fp).startswith("MISSING_MARKERS_"):
                drift.append("%s %s @ %s (该修没同步到这份!)" % (fp, name, p))
        real = [fp for fp in fps.values()
                if isinstance(fp, str) and fp not in ("ABSENT", "READ_FAIL")
                and not fp.startswith("MISSING_MARKERS_")]
        if len(set(real)) > 1:
            drift.append("LOGIC_DRIFT %s: %d 份关键逻辑不一致" % (name, len(set(real))))
    if drift:
        print("[COPY_DRIFT] 双树副本漂移/修未同步 (谁只改了一份):")
        for d in drift:
            print("  " + d)
        sys.exit(1)
    print("[COPY_DRIFT] OK: 全部副本关键逻辑一致 (%d 组 / %d 文件)"
          % (len(GROUPS), sum(len(g[1]) for g in GROUPS)))


if __name__ == "__main__":
    main()
