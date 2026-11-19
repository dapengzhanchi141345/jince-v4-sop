# -*- coding: utf-8 -*-
"""金策 L5 · SamSupplyDemand 残稿腿入 evolution_inbox (WATCH, 0 回测, 0 live)
[2026-10-11] @user 给 E:\李彦明\学习资料\ea\mt4 让吸收到系统.
@chief/@strategy-rd 实拉: SamSupplyDemand.mq4 = 331行且末行 L331 硬截断在需求区判断中间
(开仓/止损/出场逻辑缺失), 三条风控红线 grep 0 命中 (无日亏熔断/无连亏冷却/无品种日单闸).
@risk-officer L4 终裁: 残缺源腿五验①样本闸前提不成立, 补全前 0 回测 0 进 live.
本脚本 = 按 L4 口径只当"供需区回踩接势"结构参考入箱 WATCH, 焊三条红线准入.
红线: 0 改 queue 里已裁定的腿, 0 碰实盘, 历史回测≠未来收益.
"""
import json, os, time, sys

D = r"E:\GoldstrategyEngine\data"
INBOX = os.path.join(D, "evolution_inbox.json")

def main():
    ib = json.load(open(INBOX, encoding="utf-8"))
    now_ts = int(time.time())

    # 防重复入箱
    dup = [q for q in ib.get("queue", []) if "SamSupplyDemand" in json.dumps(q, ensure_ascii=False)]
    if dup:
        print("ALREADY_IN_BOX: " + json.dumps(dup[0], ensure_ascii=False)[:200])
        return 0

    entry = {
        "id": "EVO-20261011-SamSupplyDemand",
        "ts": now_ts,
        "claimed_by": "strategy-rd",
        "source": "外部学习 EA (E:\\李彦明\\学习资料\\ea\\mt4\\SamSupplyDemand.mq4, @user 给), @chief L1 实读",
        "leg_structure": "供需区回踩接势: Drop-Base-Rally(需求)/Rally-Base-Drop(供应) 盘整区识别 + 回踩次数 + 穿透25%失效 + 大周期MA50同向加分 + 离场强度得分",
        "status": "WATCH_结构参考",
        "live_flag": False,
        "backtest_allowed": False,
        "blocker_1_truncated": "源文件 331 行且 L331 硬截断在需求区判断 if(Bid<=zones[i].high && 中间, 进区后开仓/止损/出场逻辑缺失; 残缺腿同分母回测=选择效应, 五验①样本闸前提不成立, 补全前 0 回测",
        "blocker_2_no_risk_redline": "三条风控红线 grep 0 命中: 无日亏10%熔断 / 无连亏3笔24h冷却 / 无品种日≤3单计数闸 = 裸奔结构",
        "ex4_companion": "同文件夹 精控师441(89K)/连弩6.08(240K) = .ex4 编译壳读不了源码, 0 吸收; 有原始 .mq5 再深挖",
        "admission_rules_L4": [
            "进 live 前必须补全源腿(完整版源码) => 五验①样本闸读补全后的完整腿, 残稿不算启动",
            "焊死三条红线: 日亏10%熔断 ∧ 连亏3笔24h冷却 ∧ 品种日≤3单, 缺一件 L4 一票否",
            "只学结构不学仓位; 五验 5/5 (样本≈1000 / 同分母A/B / ≥4/6品种同号 / 参数邻域无翻转 / wf3) 全过才进 live",
            "残缺源腿 exp_R L4 0 认当依据 (同分母铁律)"
        ],
        "verdict": "OBSERVE",
        "verdict_reason": "L4 终裁: 残稿 0 回测 0 进 live, 只当结构参考攒样; 用户给完整版源码后重做(补全+焊三红线+五验)",
        "action": "进 OBSERVATION MODE (候选生成关, 结构参考进 WATCH), 不桥接 30min 循环闸源, 0 放大",
        "supersedes_if_complete": "若用户提供完整版源码, 本条目 supersede 重做: 补全腿+焊三红线+五验, L4 二次 APPROVE 才进 live"
    }
    ib["queue"].append(entry)
    json.dump(ib, open(INBOX, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("INBOX_ADDED: EVO-20261011-SamSupplyDemand (WATCH 结构参考, 0 回测 0 live, 三红线焊死准入)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
