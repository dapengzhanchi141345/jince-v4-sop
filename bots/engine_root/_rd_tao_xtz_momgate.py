# -*- coding: utf-8 -*-
"""tao_xtz_direction_gate_reverify 认领 (chief 10-14 亚盘半日深析 10:05 节点, @strategy-rd 进化点):
系统给 TAOUSD 判 LONG (conf 0.4) 但 24h 动量 -8.1% -> 方向层 vs 动量层打架;
XTZUSD 昨夜亚盘 LONG 0.65 / 美盘 SHORT 0.8 方向不一致 + 今早 +11.2% 异动 + 半日对账做反.
同分母铁律: 全事件集重算不是子集. 基座 = fam4 M30 D1 方向闸事件全集 x P4 协议 replay
          (复用 _rd_mom_veto_gate.replay_p4_with_i0 / z_two_prop, 与 PDD 动量门同口径同分母).
按 24h 动量 (事件bar锚点 前48根M30 收盘变化, 防前视) 顺/逆分桶,
判据: Δ=expR(contra)-expR(agree) + 两比例 z + 品种稳健 + wf3; 单品种 n<30 只作 WATCH 旁证不单独判.
纯读 tf_cache, 不连 MT5, 不碰交易配置. 未 5/5 不进 live 挂单闸."""
import sys, os, json, math
import numpy as np
ROOT = r"E:\GoldstrategyEngine"
sys.path.insert(0, ROOT)
import _night_fam4_m30_exit as fam4
import importlib.util
_spec = importlib.util.spec_from_file_location("_rd_mom_veto_gate", os.path.join(ROOT, "_rd_mom_veto_gate.py"))
mvg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mvg)
z_two_prop = mvg.z_two_prop
replay_p4_with_i0 = mvg.replay_p4_with_i0

CF = os.path.join(ROOT, "data", "tf_cache")
OUT = os.path.join(ROOT, "data", "rd_verify_batch_tao_xtz_momgate.json")
SYMS = ["TAOUSD", "XTZUSD"]   # 非 fam4 6币宇宙 -> 单品种事件集, 样本量受限


def sym_events(sym):
    """fam4.build + P4 replay + 动量分桶, 单品种. 无 npz 返回 None(数据未就位)."""
    have = all(os.path.exists(os.path.join(CF, f"{sym}_{tf}.npz")) for tf in ("M30", "D1"))
    if not have:
        return None
    ev, ctx = fam4.build(sym)
    m30 = fam4.load(sym, "M30")
    T, C = m30["t"], m30["c"]
    res = replay_p4_with_i0(ev, ctx)
    mommap = {}
    for i0, ts, trig, side in ev:
        if i0 < 49:
            continue
        mommap[i0] = float((C[i0 - 1] - C[i0 - 49]) / C[i0 - 49])  # 防前视: 只用 i0-1 及以前
    rows = []
    for i0, t_fill, side, R in res:
        mom = mommap.get(i0)
        if mom is None:
            continue
        agree = (side == 1 and mom >= 0) or (side == -1 and mom <= 0)
        rows.append((sym, int(t_fill), float(R), side, mom, bool(agree)))
    return rows


def main():
    all_rows = []
    per_sym = {}
    for sym in SYMS:
        rows = sym_events(sym)
        if rows is None:
            per_sym[sym] = {"status": "DATA_PENDING", "note": "tf_cache 无该品种 npz, 待 Phase B 释放 MT5 IPC 后拉取"}
            continue
        A = [r for r in rows if r[5]]
        X = [r for r in rows if not r[5]]
        RA = np.array([r[2] for r in A]); RX = np.array([r[2] for r in X])
        per_sym[sym] = {
            "n_events": len(rows),
            "n_agree": len(A), "n_contra": len(X),
            "exp_agree": round(float(RA.mean()), 4) if len(A) else None,
            "exp_contra": round(float(RX.mean()), 4) if len(X) else None,
            "delta": round(float(RX.mean() - RA.mean()), 4) if len(A) and len(X) else None,
            "wr_agree": round(float((RA > 0).mean()), 4) if len(A) else None,
            "wr_contra": round(float((RX > 0).mean()), 4) if len(X) else None,
            "sample_ge30": (len(A) >= 30 and len(X) >= 30),
            "supports_veto": (float(RX.mean()) <= float(RA.mean())) if len(A) and len(X) else None,
        }
        all_rows += rows
    # 合并口径 (同分母: 两品种事件并集重算, 而非只看 TAO/XTZ 各自子集)
    A = [r for r in all_rows if r[5]]
    X = [r for r in all_rows if not r[5]]
    nA, nX = len(A), len(X)
    RA = np.array([r[2] for r in A]); RX = np.array([r[2] for r in X])
    wA = int((RA > 0).sum()); wX = int((RX > 0).sum())
    z, ppool = z_two_prop(nA, wA, nX, wX)
    delta = (float(RX.mean()) - float(RA.mean())) if nA and nX else None
    ts_all = np.array([r[1] for r in all_rows])
    R_all = np.array([r[2] for r in all_rows])
    ag_all = np.array([r[5] for r in all_rows])
    wf = []
    for k in range(3):
        lo = ts_all.min() + (ts_all.max() - ts_all.min()) * k / 3
        hi = ts_all.min() + (ts_all.max() - ts_all.min()) * (k + 1) / 3
        sel = (ts_all >= lo) & (ts_all < hi) if k < 2 else (ts_all >= lo)
        a_s = R_all[sel & ag_all]; x_s = R_all[sel & ~ag_all]
        wf.append(round(float(x_s.mean() - a_s.mean()), 4) if len(a_s) and len(x_s) else None)
    data_ready = all(v.get("status") != "DATA_PENDING" for v in per_sym.values())
    five = {
        "样本>=30": bool(nA >= 30 and nX >= 30),
        "同分母delta<0(contra更差)": delta is not None and delta < 0,
        "z>=1.96": z is not None and z >= 1.96,
        "品种稳健>=4/6": None,   # 仅2品种, 稳健项不适用 -> 记 None 不判
        "wf3三段delta全<0": all(v is not None and v < 0 for v in wf) if all(v is not None for v in wf) else False,
    }
    out = {
        "item": "tao_xtz_direction_gate_reverify", "owner": "strategy-rd",
        "hypo": "TAO/XTZ 方向闸在 24h 大动量冲突下: LONG 判是真 edge 还是被大动量拖着做反 (同分母全事件集重算)",
        "base": "fam4 M30 D1方向闸事件全集 x P4协议 replay, TAOUSD+XTZUSD, 与PDD动量门同口径同分母, 防前视(动量锚点只用事件bar前48根M30)",
        "data_ready": data_ready,
        "n_total": len(all_rows), "n_agree": nA, "n_contra": nX,
        "exp_R_agree": round(float(RA.mean()), 4) if nA else None,
        "exp_R_contra": round(float(RX.mean()), 4) if nX else None,
        "delta_contra_minus_agree": round(delta, 4) if delta is not None else None,
        "wr_agree": round(wA / nA, 4) if nA else None,
        "wr_contra": round(wX / nX, 4) if nX else None,
        "z_two_prop": round(z, 3) if z is not None else None,
        "per_sym": per_sym, "wf3_delta": wf,
        "five_checks": five,
    }
    if not data_ready:
        out["verdict"] = "BLOCKED_DATA: TAO/XTZ 未在 fam4 tf_cache, 待拉 npz 后真跑; 旁证方向=方向层LONG与24h动量负向冲突, 单品种n<30只WATCH不单独判(同分母铁律)"
    else:
        out["verdict"] = ("PASS->方向闸动量冲突可提WATCH提权(5/5)" if all(v for v in five.values() if v is not None)
                          and five["wf3三段delta全<0"] else "REJECT->留WATCH, 不动live (单品种样本受限, 只作方向旁证)")
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: out[k] for k in ("data_ready", "n_total", "n_agree", "n_contra",
                                          "exp_R_agree", "exp_R_contra", "delta_contra_minus_agree",
                                          "z_two_prop", "five_checks", "verdict")}, ensure_ascii=False, indent=1))
    print("per_sym:", json.dumps(per_sym, ensure_ascii=False))


if __name__ == "__main__":
    main()
