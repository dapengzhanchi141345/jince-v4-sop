# -*- coding: utf-8 -*-
"""看板同步哨兵 09:11 异常核验: 是 git 路瞬抖(gh-api 还活) 还是全挂?
只读, 不动交易. 本地看板 mtime / 上次成功戳 / gh-api 能否推到 / 限流余量."""
import os, json, subprocess, base64, datetime, time

REPO = r"C:\Users\ASUS\jince-dashboard"
STAMP = os.path.join(REPO, ".tick_pushed")  # tick 喂戳(不同, 仅参考)
GH_REPO = "dapengzhanchi141345/jince-trading-dashboard"

print("=== 1. 本地看板 index.html mtime(最后生成) ===")
idx = os.path.join(REPO, "index.html")
if os.path.exists(idx):
    print("  mtime:", datetime.datetime.fromtimestamp(os.path.getmtime(idx)).strftime("%m-%d %H:%M:%S"))
else:
    print("  不存在:", idx)

print("=== 2. 远端 index.html 最新 commit 时间 ===")
def gh(*a, timeout=120):
    return subprocess.run(["gh", "api", "-H", "User-Agent: jince-watch", *a],
                          capture_output=True, text=True, timeout=timeout, creationflags=0x08000000)
r = gh("repos/%s/commits/main" % GH_REPO, "--jq", ".commit.committer.date")
print("  ", r.stdout.strip()[:60] if r.returncode == 0 else ("gh 失败: " + r.stderr[:120]))

print("=== 3. gh-api 现在通不通(限流余量 + 试读一个 blob) ===")
r2 = gh("rate_limit", "--jq", ".resources.core.remaining")
print("  core.remaining =", r2.stdout.strip() if r2.returncode == 0 else ("失败 " + r2.stderr[:80]))

print("=== 4. 本地板看比远端新多少(若本地 mtime 远端没有 = 待推, 下哨兵班自愈) ===")
# 取远端 index.html 内容头 100 字 vs 本地, 判是否已同步
r3 = gh("repos/%s/contents/index.html" % GH_REPO, "--jq", ".content")
if r3.returncode == 0:
    remote_head = base64.b64decode(r3.stdout).decode("utf-8", "ignore")[:80].replace("\n", " ")
    local_head = open(idx, encoding="utf-8", errors="ignore").read()[:80].replace("\n", " ")
    print("  远端头:", remote_head)
    print("  本地头:", local_head)
    print("  一致?" , "YES" if remote_head == local_head else "NO(本地有新内容待推)")
else:
    print("  读远端 index.html 失败:", r3.stderr[:120])
