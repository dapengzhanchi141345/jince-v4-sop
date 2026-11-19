# -*- coding: utf-8 -*-
"""确认远端 index.html 是否已同步: 看 index.html 的最近 3 条 commit(带路径过滤) + 重试读 contents."""
import subprocess, json, base64, time

GH_REPO = "dapengzhanchi141345/jince-trading-dashboard"

def gh(*a, timeout=120, tries=4):
    last = None
    for i in range(tries):
        r = subprocess.run(["gh", "api", "-H", "User-Agent: jince-watch", *a],
                           capture_output=True, text=True, timeout=timeout, creationflags=0x08000000)
        last = r
        if r.returncode == 0 and r.stdout.strip():
            return r
        time.sleep(2 * (i + 1))
    return last

print("=== index.html 最近 3 条 commit(路径过滤, 重试读) ===")
r = gh(f"repos/{GH_REPO}/commits?path=index.html&per_page=3", "--jq",
       ".[].commit.author.date + ' | ' + .commit.message")
if r.returncode == 0 and r.stdout.strip():
    for line in r.stdout.strip().splitlines():
        print("  ", line[:90])
else:
    print("  读失败:", r.stderr[:150])

print("=== 远端 index.html 大小 + 头 60 字(重试读) ===")
r2 = gh(f"repos/{GH_REPO}/contents/index.html", "--jq", ".size")
print("  远端 size =", r2.stdout.strip() if r2.returncode == 0 else ("失败 " + r2.stderr[:100]))
import os
local_size = os.path.get_size(r"C:\Users\ASUS\jince-dashboard\index.html")
print("  本地 size =", local_size)
