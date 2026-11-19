# -*- coding: utf-8 -*-
r"""金策·哨兵死信开关 (确定性 0LLM, 每15min cron)
治"哨兵自己也死"这一层: 每个金策活体哨靠产物文件心跳, 本哨逐一查新, 谁超期=点名。
全绿=stdout空(不投递); 有超期=列出名单+各自最后心跳, 静默失败从此不存在。
11-14 李彦明令"所有问题处理好+深度预防机制"落地件之一。
"""
import os, glob, json
import time
import datetime

BJT = datetime.timezone(datetime.timedelta(hours=8))
DATA = r"E:\GoldstrategyEngine\data"

# (产物文件, 超期分钟, 谁的心跳, 死了谁报警)
WATCH = [
    (os.path.join(DATA, "live24_magic_30261103.lock"), 10, "live24引擎心跳"),
    (r"E:\AgentCommons\shared\live_state.json", 35, "共同体实盘真值(yushi写)"),
    (os.path.join(DATA, "bridge_adapt_state.json"), 90, "换网自适应哨(30min)"),
    (os.path.join(DATA, "exec_preflight_selftest.json"), 1500, "执行预检日检(07:30)"),
    (None, 20 * 60, "研发活体台账组(任一1200min内动=活跃)"),  # [11-15修] 原单读rd_or_review_24h假点名, 10-12误报源修复漏改本文件
]


def main():
    now = time.time()
    stale = []
    missing = []
    for path, max_min, label in WATCH:
        if path is None:
            # [11-15] 研发活体台账组: 取组内最新 mtime (对齐 jince_heartbeat_watch.py 10-12 修复口径)
            group = ["rd_or_review_24h.json", "rd_queue.json", "meta_evolution.json",
                     "governor_state.json", "rd_ledger_24h.json"]
            ts = [os.path.getmtime(os.path.join(DATA, f)) for f in group if os.path.exists(os.path.join(DATA, f))]
            ts += [os.path.getmtime(f) for f in glob.glob(os.path.join(DATA, "rd_verify_batch_*.json"))]
            if not ts:
                missing.append(label + " [活体台账组全部缺失]")
                continue
            newest = max(ts)
        elif not os.path.exists(path):
            missing.append(label + " [" + path + " 不存在]")
            continue
        else:
            newest = os.path.getmtime(path)
        age_min = (now - newest) / 60.0
        if age_min > max_min:
            last = datetime.datetime.fromtimestamp(newest, BJT).strftime("%m-%d %H:%M")
            # [11-16] RETIRE旗豁免: live24_retire.json active=true 时引擎down=L5裁定在案(翻旗等李彦明), 豁免红报防逐拍噪音; 旗翻 active=false 后照旧红报
            if label.startswith("live24引擎心跳"):
                _ret_active = False
                try:
                    _rf = os.path.join(DATA, "live24_retire.json")
                    if os.path.exists(_rf):
                        _ret_active = bool(json.load(open(_rf, encoding="utf-8")).get("active"))
                except Exception:
                    pass
                if _ret_active:
                    continue  # L5 在案, 静默
            stale.append("%s: 最后心跳 %s 前%.0f分钟 (限%dmin)" % (label, last, age_min, max_min))
        continue
        age_min = (now - os.path.getmtime(path)) / 60.0
        if age_min > max_min:
            last = datetime.datetime.fromtimestamp(os.path.getmtime(path), BJT).strftime("%m-%d %H:%M")
            stale.append("%s: 最后心跳 %s 前%.0f分钟 (限%dmin)" % (label, last, age_min, max_min))
    if stale or missing:
        print("⚠️ 哨兵死信开关·点名 %s (超期%d 缺失%d):" % (
            datetime.datetime.now(BJT).strftime("%m-%d %H:%M"), len(stale), len(missing)))
        for s in stale:
            print("  超期:", s)
        for m in missing:
            print("  缺失:", m)
        print("处置: 逐个拉起对应哨/脚本, 修根因留痕 task_ledger")
    # 全绿=空stdout(不投递); 点名=有stdout(投递)
    return 0


if __name__ == "__main__":
    main()
