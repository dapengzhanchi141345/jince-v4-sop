# -*- coding: utf-8 -*-
"""02:00 学科站 升级+部署 串行包装(确定性 0 LLM, 供 cron 单 script 字段接线):
① sites_daily_upgrade.py  本地 12 站增量升级(防刷数)
② sites_deploy_12indep.py gh-api 推 12 个独立 Pages 仓(根治 10-08 发现的漏部署)
任一失败 -> exit 1(让 cron 异常发声, 不静默吞)."""
import subprocess, sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
for name in ("sites_daily_upgrade.py", "sites_deploy_12indep.py"):
    print(f"=== [{name}] start ===")
    r = subprocess.run([PY, os.path.join(HERE, name)], timeout=900, creationflags=0x08000000)
    if r.returncode != 0:
        print(f"[失败] {name} exit={r.returncode}")
        sys.exit(1)
print("[完成] 12独立站 升级+部署 全链 OK")
