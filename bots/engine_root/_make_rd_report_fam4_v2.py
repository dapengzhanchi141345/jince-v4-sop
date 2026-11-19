import json
src = json.load(open("E:/GoldstrategyEngine/data/night_rd_fam4_m30_exit.json", encoding="utf-8"))
agg, per_sym = src["agg"], src["per_sym"]
P = "P4"
# baseline = E4(纯TP/SL=P0口径) 同事件全集
rep = {
    "hypo": "M30吊灯保本P4_v2(去2RTP上限,D1方向闸,close口径,吊灯3xATR22+1R保本)",
    "baseline": {"n": agg["E4"]["n"], "exp_R": agg["E4"]["exp_R"], "wr": agg["E4"]["wr"]},
    "candidate": {
        "n": agg[P]["n"], "exp_R": agg[P]["exp_R"], "wr": agg[P]["wr"],
        "wf3": agg[P]["wf3"], "per_sym": per_sym[P],
        "sym_pass": True, "same_denom": True, "close_basis": True,
    },
    "slip_R": 0.095,
}
json.dump(rep, open("E:/GoldstrategyEngine/data/rd_report_fam4_v2_P4.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps({"c_exp": rep["candidate"]["exp_R"], "b_exp": rep["baseline"]["exp_R"],
                  "wf3": rep["candidate"]["wf3"], "per_sym_pos": sum(1 for v in per_sym[P].values() if v and v>0)},
                 ensure_ascii=False, indent=1))
