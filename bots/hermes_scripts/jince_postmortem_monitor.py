# 验尸官(post-mortem)交付监测 (每日10:15哨): 全绿静默(空输出=不发), 停滞/逾期才出声
import os, time
ROOT = r"E:/GoldstrategyEngine/data/postmortem"
now = time.time()
if not os.path.isdir(ROOT):
    print("⚠️ [验尸官监测] 复盘归档目录未建(E:/GoldstrategyEngine/data/postmortem 不存在) — 首交期限11-13 09:00, 逾期即红报点名@post-mortem")
else:
    files = [f for f in os.listdir(ROOT) if f.endswith('.json')]
    if not files:
        print("⚠️ [验尸官监测] 目录在但0归档 — 首交期限11-13 09:00, 逾期即红报点名@post-mortem")
    else:
        latest = max(os.path.getmtime(os.path.join(ROOT, f)) for f in files)
        age_h = (now - latest) / 3600
        if age_h > 26:
            print("⚠️ [验尸官监测] 复盘归档已%.0fh未更新(>26h停滞) — 点名@post-mortem, >46h无产出升红报报李彦明" % age_h)
        # 全绿(26h内有更新)=空输出=哨静默
