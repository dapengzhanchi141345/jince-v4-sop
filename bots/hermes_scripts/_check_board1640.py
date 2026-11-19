# -*- coding: utf-8 -*-
"""16:40 看板同步失败核验: git 路抖还是全挂 / 本地 vs 远端新多少 / gh-api 通不通(只读)"""
import os, json, subprocess, base64, datetime

REPO = r"C:\Users\ASUS\jince-dashboard"
GH_REPO = "dapengzhanchi141345/jince-trading-dashboard"
idx = os.path.join(REPO, "index.html")

def gh(*a, timeout=90, tries=4):
    last = None
    import time
    for i in range(tries):
        r = subprocess.run(["gh", "api", "-H", "User-Agent: jince-watch", *a],
                           capture_output=True, text=True, timeout=timeout, creationflags=0x08000000)
        last = r
        if r.returncode == 0 and r.stdout.strip():
            return r
        time.sleep(2 * (i + 1))
    return last

print("=== 1. 本地板看 mtime + 远端最新 commit 时间 ===")
print("  本地 index.html mtime:",
      datetime.datetime.fromtimestamp(os.path.getmtime(idx)).strftime("%m-%d %H:%M:%S") if os.path.exists(idx) else "不存在")
r = gh("repos/%s/commits/main" % GH_REPO, "--jq", ".commit.committer.date")
print("  远端 main HEAD:", r.stdout.strip() if r.returncode == 0 else ("gh 失败 " + r.stderr[:100]))

print("\n=== 2. gh-api 通不通(限流 + 远端 index.html 头) ===")
r2 = gh("rate_limit", "--jq", ".resources.core.remaining")
print("  core.remaining =", r2.stdout.strip() if r2.returncode == 0 else ("失败 " + r2.stderr[:80]))
r3 = gh("repos/%s/contents/index.html" % GH_REPO, "--jq", ".size")
print("  远端 index.html size =", r3.stdout.strip() if r3.returncode == 0 else ("读失败 " + r3.stderr[:80]))
print("  本地 index.html size =", os.path.getsize(idx) if os.path.exists(idx) else "N/A")

print("\n=== 3. 判级 ===")
print("  若 gh-api 能读远端(余量>0) => git 路瞬抖, gh-api 兜底 10min 内自愈, 无需动作")
print("  若 gh-api 也读不动 => 墙真堵到 API 腿, 需人工介入(换 IP/重启路由)")
