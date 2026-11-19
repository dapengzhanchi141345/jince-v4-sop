"""train_meta_filter.py — P1-1 Meta-Labeling 训练 (2026-09-06 刷新)

用引擎自有回测语料 data/portfolio_trades_KEEP.csv (8196 笔, 2023-03-09~2026-08-12)
真实训练 `meta_label_filter.MetaFilter`：主信号(规则策略)→ 次模型预测该信号是否盈利
→ 按置信度(阈值 0.65)过滤假阳性 + 缩放仓位。落地 López de Prado 哲学。

防泄露纪律（mlq.ai 2026 / mental-momentum 2026）：
  - **禁止随机 k-fold**：按时间顺序切 80% 训练 / 20% 样本外（OOS 在最近期）。
  - 特征仅用信号时刻可得量（策略族/方向/风险预算标准化/|R|），不含未来信息。
  - 类别权重处理胜率不均衡（win~44%），与 8-31 逻辑一致，现经 MetaFilter.sample_weight 落地。

输出：validation/meta_filter_proof_20260906.json（刷新 8-31 概念验证，确认机制可复现）
纯 numpy（无 sklearn/scipy）。
"""
from __future__ import annotations
import csv
import json
import os
import sys
from datetime import datetime

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from meta_label_filter import MetaFilter

FAMILIES = ["TREND", "BO", "ICT", "DIV", "MR", "VP", "SDP"]
CSV_PATH = "data/portfolio_trades_KEEP.csv"
OUT_JSON = "validation/meta_filter_proof_20260906.json"
THRESH = 0.65
TRAIN_RATIO = 0.8


def _family(s: str) -> str:
    u = s.upper()
    for k in FAMILIES:
        if k in u:
            return k
    return "SDP"


def load(path):
    rows = []
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            rows.append(r)
    rows.sort(key=lambda x: x["ts"])
    return rows


def build_features(rows):
    by_sym_risk = {}
    for r in rows:
        by_sym_risk.setdefault(r["sym"], []).append(float(r["risk"]))
    sym_mean = {s: np.mean(v) for s, v in by_sym_risk.items()}
    sym_std = {s: (np.std(v) + 1e-9) for s, v in by_sym_risk.items()}
    X, y = [], []
    for r in rows:
        fam = _family(r["strat"])
        x = [1.0 if f == fam else 0.0 for f in FAMILIES]
        x.append(float(r["side"]))
        x.append((float(r["risk"]) - sym_mean[r["sym"]]) / sym_std[r["sym"]])
        x.append(abs(float(r["R"])))
        X.append(x)
        y.append(1.0 if float(r["profit"]) > 0 else 0.0)
    return np.array(X, dtype=float), np.array(y, dtype=float)


def auc_score(y, p):
    """Mann-Whitney U 估计 AUC（处理并列，无 sklearn）。"""
    y = np.asarray(y); p = np.asarray(p)
    pos = p[y == 1]; neg = p[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    cnt_less = np.sum(neg[:, None] < pos[None, :], axis=1)
    cnt_eq = np.sum(neg[:, None] == pos[None, :], axis=1)
    u = cnt_less.sum() + 0.5 * cnt_eq.sum()
    return u / (len(pos) * len(neg))


def main():
    root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(root)
    rows = load(CSV_PATH)
    X, y = build_features(rows)
    n = len(y)
    k = int(n * TRAIN_RATIO)
    Xtr, ytr = X[:k], y[:k]
    Xte, yte = X[k:], y[k:]

    pos = max(ytr.mean(), 1e-3)
    sw = np.where(ytr == 1, 1.0 / pos, 1.0 / (1 - pos))   # 类别权重

    mf = MetaFilter(lr=0.05, n_iter=800, threshold=THRESH)
    mf.fit(Xtr, ytr, sample_weight=sw)

    pte = mf.predict_proba(Xte)
    oos_auc = auc_score(yte, pte)
    base_wr = float(yte.mean())
    passed = pte >= THRESH
    filt_wr = float(yte[passed].mean()) if passed.sum() > 0 else 0.0
    coverage = float(passed.mean())
    lift = (filt_wr / base_wr - 1.0) * 100 if base_wr > 0 else 0.0
    ptr = mf.predict_proba(Xtr)
    train_auc = auc_score(ytr, ptr)

    out = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "source": CSV_PATH,
        "n_total": n, "n_train": k, "n_oos": n - k,
        "features": FAMILIES + ["side", "risk_norm", "absR"],
        "split": "chronological 80/20 (NO random k-fold)",
        "threshold": THRESH,
        "train_auc": round(float(train_auc), 4),
        "oos_auc": round(float(oos_auc), 4),
        "base_win_rate_oos": round(base_wr, 4),
        "filtered_coverage": round(coverage, 4),
        "filtered_win_rate_oos": round(filt_wr, 4),
        "win_rate_lift_pct": round(float(lift), 2),
        "family_weights": {FAMILIES[i]: round(float(mf.w[i]), 4) for i in range(len(FAMILIES))},
        "side_w": round(float(mf.w[7]), 4),
        "risk_w": round(float(mf.w[8]), 4),
        "absR_w": round(float(mf.w[9]), 4),
        "note": "真实引擎语料训练, 次模型过滤假阳性; 生产可换 mlfinpy/LightGBM",
    }
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("=" * 64)
    print("P1-1 Meta-Labeling 训练 (真实引擎语料, 2026-09-06)")
    print("=" * 64)
    print(f"样本: {n} | 训练 {k} | OOS {n-k} | 特征 {len(out['features'])}")
    print(f"OOS AUC        = {oos_auc:.4f}  (参考 8-31 概念验证 0.7371)")
    print(f"基准 OOS 胜率  = {base_wr*100:.1f}%")
    print(f"过滤后 OOS 胜率= {filt_wr*100:.1f}% (覆盖 {coverage*100:.1f}%)")
    print(f"胜率提升       = {lift:+.1f}%")
    print(f"已写出: {OUT_JSON}")


if __name__ == "__main__":
    main()
