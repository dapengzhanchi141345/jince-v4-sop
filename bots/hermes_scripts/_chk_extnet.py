# -*- coding: utf-8 -*-
"""extnet=down 抖了~129min: 真断还是探活误报? 探 gh-api + 公网 200 两条腿(只读, 不写交易配置)"""
import subprocess, time
_HIDE = 0x08000000 if __import__("os").name == "nt" else 0  # CREATE_NO_WINDOW [后台化: gh/git/curl 子进程不闪窗]

def run(cmd, t=15):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=t, creationflags=_HIDE)
        return (r.returncode, (r.stdout or "").strip()[:300])
    except subprocess.TimeoutExpired:
        return ("TO", "timeout")
    except Exception as e:
        return ("ERR", str(e)[:100])

# 1) 外网基础通不通: api.github.com (不 443 墙)
rc, out = run('gh api rate_limit --jq .resources.core.remaining 2>&1')
print(f"gh-api rate_limit: rc={rc} out={out[:80]}")

# 2) 公网 200 验: 某站 Pages(走 gh 公网 DNS)
import glob
t=f'E:/workbuddy/内容中心/网站/进度台账/网站独立站台账.json'
try:
    import json
    d=json.load(open(t,encoding='utf-8'))
    # 找第一个 url
    u=None
    for k,v in (d.items() if isinstance(d,dict) else []):
        if isinstance(v,dict) and v.get('url'): u=v['url']; break
    print("验 200 的站:", u)
    if u:
        rc2,out2 = run(f'curl -s -o NUL -w "%{{http_code}}" --max-time 12 "{u}" 2>&1', 20)
        print(f"公网200: rc={rc2} http={out2}")
except Exception as e:
    print("验200异常:", e)

# 3) 直连 github.com:443 (git 路, 443 墙探活这条腿)
rc3,out3 = run('curl -s -o NUL -w "%{{http_code}}" --max-time 10 https://github.com 2>&1', 15)
print(f"github.com:443: rc={rc3} http={out3}")

print("=== 判定 ===")
