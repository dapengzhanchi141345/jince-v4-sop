# -*- coding: utf-8 -*-
"""tao_xtz_dirjoin 同分母方向对账 (chief 10-14 亚盘半日深析 10:05 节点, @strategy-rd):
问题: 系统给 TAOUSD 判 LONG(conf 0.4) 但 24h 动量 -8.1% -> 方向层与动量层打架,
     LONG 判在大动量下是真 edge 还是被拖着做反? XTZUSD 同族(昨夜亚盘LONG 0.65/美盘SHORT 0.8
     方向不一致 + 今早+11.2%异动 + 半日对账做反).
口径: advisory(方向研判+研判时点 mom_m30_24h, daily_advisory_YYYYMMDD) JOIN reflection
     (当日方向对账结果 WIN/MISS/LOSS/DIRECTION_HIT, 日期归一化 YYYYMMDD), 全事件集同分母重算,
     按 研判时点动量 顺/逆分桶(agree=顺向, contra=冲突), 算胜率 + 两比例 z.
铁律: 方向对账=方向闸层准确率, 非开单 R 期望; 高胜率≠正期望, 本批只出"是否做反"判定,
     不正向提权(五验 R 层 = _rd_tao_xtz_momgate.py fam4 replay, 待 tf_cache 补 npz 后跑).
纯读 json, 不连 MT5, 不碰交易配置."""
import json, glob, math, os
ROOT = r"E:\GoldstrategyEngine"
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(DATA, "rd_verify_batch_tao_xtz_dirjoin.json")


def main():
    refl = json.load(open(os.path.join(DATA, "advisory_reflection.json"), encoding="utf-8"))
    res, dirmap, confmap = {}, {}, {}
    for r in refl.get("records", []):
        if isinstance(r, list) and len(r) >= 9 and r[0] in ("TAOUSD", "XTZUSD"):
            k = (r[0], r[1].replace("-", ""), r[2])  # 日期归一化
            res[k], dirmap[k], confmap[k] = r[8], r[3], r[4]
    mom = {}
    for f in glob.glob(os.path.join(DATA, "daily_advisory_2026*.json")):
        day = os.path.basename(f).replace("daily_advisory_", "").replace(".json", "")
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        for sec in d.get("sections", []):
            s = sec.get("session", "?")
            for it in sec.get("items", []):
                if it.get("sym") in ("TAOUSD", "XTZUSD") and it.get("mom_m30_24h") is not None:
                    mom[(it["sym"], day, s)] = it["mom_m30_24h"] / 100.0
    out = {"item": "tao_xtz_dirjoin", "owner": "strategy-rd",
           "hypo": "TAO/XTZ 方向闸 LONG 判在 24h 大动量冲突下是真 edge 还是被拖着做反 (同分母全事件集, 研判时点动量分桶)",
           "base": "advisory方向研判(含mom_m30_24h) JOIN reflection方向对账结果, 日期归一化YYYYMMDD, 全事件集同分母",
           "per_sym": {}}
    for sym in ("TAOUSD", "XTZUSD"):
        A = [0, 0]; X = [0, 0]
        big_conf = []
        matched = 0
        for k in res:
            s_, day, sess = k
            if s_ != sym:
                continue
            m = mom.get(k); d = dirmap[k]
            if m is None or d is None:
                continue
            matched += 1
            hit = 1 if res[k] == "WIN" else 0
            agree = (d == "LONG" and m >= 0) or (d == "SHORT" and m <= 0)
            if agree:
                A[0] += 1; A[1] += hit
            else:
                X[0] += 1; X[1] += hit
                if abs(m) >= 0.05:
                    big_conf.append({"date": day, "sess": sess, "dir": d, "conf": confmap.get(k),
                                      "mom_pct": round(m * 100, 3), "hit": bool(hit)})
        nA, nX, wA, wX = A[0], X[0], A[1], X[1]
        p1, p2 = wA / nA if nA else 0.0, wX / nX if nX else 0.0
        z = None
        if nA and nX:
            p = (wA + wX) / (nA + nX)
            se = math.sqrt(p * (1 - p) * (1 / nA + 1 / nX))
            z = (p1 - p2) / se if se > 0 else None
        out["per_sym"][sym] = {
            "matched": matched, "n_agree": nA, "n_contra": nX,
            "wr_agree": round(p1, 4), "wr_contra": round(p2, 4),
            "z_agree_minus_contra": round(z, 3) if z is not None else None,
            "z_meaning": "z>0=顺向桶方向对账更高=动量冲突在做反; z<0=冲突桶反而更高=没被拖着做反",
            "big_contra_n": len(big_conf), "big_contra_win": sum(1 for b in big_conf if b["hit"]),
            "big_contra_events": big_conf,
            "verdict_z": None, "verdict_note": None,
        }
        v = out["per_sym"][sym]
        if z is None:
            v["verdict_z"] = "样本不足(桶n<1)"
        elif abs(z) < 1.96:
            v["verdict_z"] = "不显著(|z|<1.96): 大动量冲突下方向对账无统计差异, 判'做反'不成立但也没edge证据"
        else:
            v["verdict_z"] = ("z=%.3f: 顺向桶显著更高=动量冲突在做反(方向闸受大动量拖累)" % z
                              if z > 0 else
                              "z=%.3f: 冲突桶显著更高=没被大动量拖着做反, 冲突期方向闸反而更准(与PDD动量门'冲突更危险'假设相反, 只可当旁证不可正向提权)" % z)
    # 总判定: 同分母铁律 - 单品种桶 n<30 不单独判, 只WATCH旁证
    out["five_gate_note"] = "本批=方向对账准确率层(高胜率≠正期望铁律), 非R期望五验; 单品种桶n=12-18<30 只作WATCH旁证, 不动live; R层五验走 _rd_tao_xtz_momgate.py(fam4 replay, 待补npz)"
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: out[k] for k in ("item", "hypo", "base", "per_sym", "five_gate_note")},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
