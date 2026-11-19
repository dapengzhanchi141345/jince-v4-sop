"""
A.T.E. Deep Learning Optimizer — 盘感神经网络 v1.0
==================================================
用 "真实行情前向收益 (主) + Trading Central 共识 (老师正则)" 双信号训练,
让引擎的偏置判断具备从数据中长出来的 "盘感",
替代 continuous_evolution_v2.py 的随机模拟器。

模型: IntuitionNet (紧凑 MLP, ~1.2K 参数, 防过拟合)
  - 输入: 31 维多时间框架工程特征 (与 v2.0-DW 分析器同源)
  - 输出: 方向(UP/DOWN/FLAT) + 置信度(0-1) + 评分加成
  - 训练: 主任务 = 前向收益方向(真 alpha); 辅助 = TC 共识对齐(老师)

接口:
  DLOptimizer.load()                -> 加载已训练模型(无则返回 None)
  DLOptimizer.train_on_mt5(symbols) -> 用真实 MT5 历史训练并保存
  DLOptimizer.boost_from_raw(...)   -> (dl_dir, dl_conf, score_adjust) 接入分析器
  run_smoke_test()                  -> 合成数据训练, 验证可学性(无 MT5 也能跑)
"""
import os, json, math, warnings
import numpy as np
import pandas as pd
warnings.filterwarnings('ignore')

BASE = r"E:\GoldstrategyEngine"
MODEL_DIR = os.path.join(BASE, "models")
MODEL_PATH = os.path.join(MODEL_DIR, "intuition_net.pt")
os.makedirs(MODEL_DIR, exist_ok=True)

# ═══════════════════════════════════════════════
# 特征定义 (顺序即模型输入顺序, 训练/推理必须一致)
# ═══════════════════════════════════════════════
FEATURE_NAMES = [
    "rsi_norm", "adx_norm", "macd_hist_norm", "bb_pos",
    "ema9_dist", "ema21_dist", "ema50_dist", "ma20_dist", "price_vs_pivot",
    "atr_norm", "vol_ratio", "roc_5", "roc_20",
    "daily_bias", "h4_bias", "d1_bias", "weekly_bias",
    "dw_conf", "dw_status_enc", "tc_signal", "tc_consistent", "tc_stale",
    "support_dist", "resistance_dist", "target_dist",
    "hour_sin", "hour_cos", "momentum_enc", "macd_sig_enc",
    "score_norm", "range_norm",
]
N_FEAT = len(FEATURE_NAMES)  # 31

# 类别映射: 0=DOWN, 1=FLAT, 2=UP
CLASS_DOWN, CLASS_FLAT, CLASS_UP = 0, 1, 2

# ═══════════════════════════════════════════════
# 编码工具
# ═══════════════════════════════════════════════
def _enc_bias(s):
    s = (s or "").upper()
    if "BULL" in s or s in ("BUY", "LONG", "看多", "多"): return 1.0
    if "BEAR" in s or s in ("SELL", "SHORT", "看空", "空"): return -1.0
    return 0.0

def _enc_dw_status(v1, v4, vd, wk):
    if wk == 0: return 0.5
    if v1 == wk and v4 == wk: return 1.0      # AGREE
    if v1 == -wk and wk != 0: return -1.0     # CONFLICT
    return 0.5                                 # WEAK

def _enc_consistent(eng, tc):
    if tc == 0: return 0.0
    if eng == tc: return 1.0
    if eng == 0 or tc == 0: return 0.5
    return -1.0

def _enc_momentum(rsi):
    if rsi > 65: return -1.0
    if rsi > 55: return -0.5
    if rsi < 35: return 1.0
    if rsi < 45: return 0.5
    return 0.0

def _enc_macd_sig(line, hist, hist5):
    if line > 0 and hist > hist5: return 1.0
    if line < 0 and hist < hist5: return -1.0
    if line > 0: return 0.5
    if line < 0: return -0.5
    return 0.0

# ═══════════════════════════════════════════════
# 指标引擎 (模块自包含, 不依赖 technical_analyzer)
# ═══════════════════════════════════════════════
def _ema(v, p):
    v = np.asarray(v, float); n = len(v)
    if n < p: return v.astype(float)
    r = np.full(n, np.nan); r[p-1] = np.mean(v[:p]); a = 2/(p+1)
    for i in range(p, n): r[i] = v[i]*a + r[i-1]*(1-a)
    return r

def _atr(h, l, c, p=14):
    h, l, c = np.asarray(h, float), np.asarray(l, float), np.asarray(c, float); n = len(c)
    tr = np.zeros(n)
    up = h[1:]-h[:-1]; dn = l[:-1]-l[1:]
    tr[1:] = np.maximum(up, np.maximum(np.abs(up - (-dn)), np.abs(dn)))
    # 上面写法只为占位, 真正用标准公式:
    tr[1:] = np.maximum(h[1:]-l[1:], np.maximum(np.abs(h[1:]-c[:-1]), np.abs(l[1:]-c[:-1])))
    r = np.full(n, np.nan); r[p] = np.mean(tr[1:p+1])
    for i in range(p+1, n): r[i] = tr[i]/p + r[i-1]*(1-1/p)
    return np.nan_to_num(r, nan=np.mean(tr[1:p+1]))

def _rsi(c, p=14):
    c = np.asarray(c, float); d = np.diff(c)
    g = pd.Series(np.where(d > 0, d, 0.0)).ewm(alpha=1/p, adjust=False).mean().values
    lo = pd.Series(np.where(d < 0, -d, 0.0)).ewm(alpha=1/p, adjust=False).mean().values
    rs = g/(lo + 1e-10)
    return 100 - 100/(1+rs)

def _macd(c, fast=12, slow=26, sig=9):
    c = np.asarray(c, float)
    line = _ema(c, fast) - _ema(c, slow)
    esig = _ema(line, sig)
    return line, esig, line - esig

def _bollinger(c, p=20, m=2):
    c = np.asarray(c, float)
    mid = pd.Series(c).rolling(p).mean().values
    sd = pd.Series(c).rolling(p).std().values
    return mid - m*sd, mid, mid + m*sd

def _adx(h, l, c, p=14):
    h, l, c = np.asarray(h, float), np.asarray(l, float), np.asarray(c, float); n = len(c)
    up = h[1:]-h[:-1]; dn = l[:-1]-l[1:]
    plus_dm = np.zeros(n); plus_dm[1:] = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.zeros(n); minus_dm[1:] = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = _atr(h, l, c, p)
    plus_di = 100*_ema(plus_dm, p)/(tr + 1e-10)
    minus_di = 100*_ema(minus_dm, p)/(tr + 1e-10)
    dx = 100*np.abs(plus_di - minus_di)/(plus_di + minus_di + 1e-10)
    return _ema(dx, p)

def _votes(c1, c4, c1d):
    e9 = _ema(c1, 9); e21 = _ema(c1, 21); e50 = _ema(c1, 50)
    h4e21 = _ema(c4, 21); h4e50 = _ema(c4, 50)
    d1e21 = _ema(c1d, 21); d1e50 = _ema(c1d, 50)
    p = float(c1[-1])
    v1 = 1 if (p > e9[-1] > e21[-1]) else -1
    v4 = 1 if (float(c4[-1]) > h4e21[-1] > h4e50[-1]) else -1
    vd = 1 if (float(c1d[-1]) > d1e21[-1] > d1e50[-1]) else -1
    return float(v1), float(v4), float(vd)

def _pivot(h, l, c, w=20):
    ph = np.max(h[-w:]); pl = np.min(l[-w:]); pc = float(c[-1])
    pp = (ph+pl+pc)/3; rng = ph-pl
    return {'PP': pp, 'R1': pp+rng*0.5, 'R2': pp+rng, 'R3': pp+rng*1.5,
            'S1': pp-rng*0.5, 'S2': pp-rng, 'S3': pp-rng*1.5, 'Range': rng}

def _weekly_dir(w1, i):
    if w1 is None or len(w1['close']) <= 21: return 0.0
    c = w1['close'].values[:i+1]; e21 = _ema(c, 21); e50 = _ema(c, 50)
    return 1.0 if float(c[-1]) > e21[-1] > e50[-1] else (-1.0 if float(c[-1]) < e21[-1] < e50[-1] else 0.0)

def _window_upto(df, t, n=240):
    """取 df 中时间 <= t 的最后 n 根 (多TF时间对齐用) — 修复 H1 索引 i 直接套 H4/D1 的错位"""
    if df is None:
        return None
    times = np.asarray(df['time'].values)
    mask = times <= t
    idx = np.flatnonzero(mask)
    if len(idx) == 0:
        return None
    end = int(idx[-1]) + 1
    start = max(0, end - n)
    return df.iloc[start:end]

def _weekly_dir_arr(cw):
    """从已时间对齐的周线收盘价数组判断方向"""
    if cw is None or len(cw) <= 21: return 0.0
    e21 = _ema(cw, 21); e50 = _ema(cw, 50)
    return 1.0 if float(cw[-1]) > e21[-1] > e50[-1] else (-1.0 if float(cw[-1]) < e21[-1] < e50[-1] else 0.0)

# ═══════════════════════════════════════════════
# 特征拼装 (训练 / 推理共用同一函数 → 分布一致)
# ═══════════════════════════════════════════════
def compute_scalar_features(h1, h4, d1, w1, i, tc_dir, tc_stale):
    """在 index i (H1) 处, 用时间对齐到 t_i 的多TF数据计算 31 维特征"""
    t_i = h1['time'].values[i]
    c1 = h1['close'].values[:i+1]; hgh = h1['high'].values[:i+1]; low = h1['low'].values[:i+1]
    if len(c1) < 55:
        return None
    # ── 多TF时间对齐: 取各TF时间<=t_i的最后窗口 (修复H1索引i直接套H4/D1的错位bug) ──
    h4w = _window_upto(h4, t_i); d1w = _window_upto(d1, t_i); w1w = _window_upto(w1, t_i)
    c4 = h4w['close'].values if h4w is not None else c1
    cd = d1w['close'].values if d1w is not None else c1
    cw = w1w['close'].values if w1w is not None else None
    price = float(c1[-1])
    rsi = float(_rsi(c1)[-1]); rsi_n = rsi/100.0
    adxv = float(_adx(hgh, low, c1)[-1])/100.0
    _, _, mhist = _macd(c1); mh = float(mhist[-1])
    bl, bm, bu = _bollinger(c1)
    bbpos = float((price - bl[-1])/(bu[-1] - bl[-1] + 1e-10))
    e9 = _ema(c1, 9); e21 = _ema(c1, 21); e50 = _ema(c1, 50)
    ma20 = pd.Series(c1).rolling(20).mean().values
    ema9d = (price - e9[-1])/price; ema21d = (price - e21[-1])/price
    ema50d = (price - e50[-1])/price; ma20d = (price - ma20[-1])/price
    pp = _pivot(hgh, low, c1)
    pvp = (price - pp['PP'])/price
    atr_n = float(_atr(hgh, low, c1)[-1])/price
    hr = hgh[-1] - low[-1]
    volr = hr/(np.mean(hgh[-20:] - low[-20:]) + 1e-10)
    roc5 = (c1[-1]/c1[-6] - 1) if len(c1) > 6 else 0.0
    roc20 = (c1[-1]/c1[-21] - 1) if len(c1) > 21 else 0.0
    v1, v4, vd = _votes(c1, c4, cd)
    wk = _weekly_dir_arr(cw)
    dws = _enc_dw_status(v1, v4, vd, wk)
    dwc = 1.0 if (wk != 0 and v1 == wk) else (0.1 if (wk != 0 and v1 == -wk) else 0.5)
    tcsig = _enc_bias(tc_dir)
    tccons = _enc_consistent(v1, tcsig)
    # 支撑/阻力距离
    res_cands = [pp['R1'], pp['R2'], pp['R3']]
    sup_cands = [pp['S1'], pp['S2'], pp['S3']]
    near_res = min(res_cands, key=lambda x: abs(x - price))
    near_sup = min(sup_cands, key=lambda x: abs(x - price))
    res_dist = (near_res - price)/price
    sup_dist = (price - near_sup)/price
    tgt = pp['S3'] if tcsig >= 0 else pp['R3']
    tgt_dist = (tgt - price)/price
    try:
        hour = pd.to_datetime(h1['time'].values[i]).hour
    except Exception:
        hour = 0
    hs = math.sin(2*math.pi*hour/24); hc_ = math.cos(2*math.pi*hour/24)
    mom = _enc_momentum(rsi)
    mline, _, _ = _macd(c1); mline = float(mline[-1])
    msig = _enc_macd_sig(mline, mh, float(mhist[-5]) if len(mhist) > 5 else mh)
    score = v1*2 + (1 if rsi < 45 else (-1 if rsi > 55 else 0)) + (1 if mh > 0 else -1 if mh < 0 else 0)
    score_n = float(np.clip(score/10.0, -1, 1))
    rangen = pp['Range']/price
    f = {
        "rsi_norm": rsi_n, "adx_norm": adxv, "macd_hist_norm": float(np.clip(mh/price*100, -1, 1)),
        "bb_pos": float(np.clip(bbpos, 0, 1)),
        "ema9_dist": ema9d, "ema21_dist": ema21d, "ema50_dist": ema50d, "ma20_dist": ma20d, "price_vs_pivot": pvp,
        "atr_norm": atr_n, "vol_ratio": float(np.clip(volr, 0, 5)), "roc_5": float(np.clip(roc5, -0.1, 0.1)),
        "roc_20": float(np.clip(roc20, -0.2, 0.2)),
        "daily_bias": v1, "h4_bias": v4, "d1_bias": vd, "weekly_bias": wk,
        "dw_conf": dwc, "dw_status_enc": dws, "tc_signal": tcsig, "tc_consistent": tccons, "tc_stale": (1.0 if tc_stale else 0.0),
        "support_dist": sup_dist, "resistance_dist": res_dist, "target_dist": tgt_dist,
        "hour_sin": hs, "hour_cos": hc_, "momentum_enc": mom, "macd_sig_enc": msig,
        "score_norm": score_n, "range_norm": float(np.clip(rangen, 0, 0.1)),
    }
    # 有限值清洗 (防 NaN/Inf 污染梯度)
    out = {}
    for nm in FEATURE_NAMES:
        v = f[nm]
        if not math.isfinite(v):
            v = 0.0
        out[nm] = float(np.clip(v, -5.0, 5.0))
    return out

def features_to_vector(fdict):
    return np.array([float(fdict[n]) for n in FEATURE_NAMES], dtype=np.float32)

# ═══════════════════════════════════════════════
# 模型
# ═══════════════════════════════════════════════
try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    TORCH_AVAILABLE = True
    DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    class IntuitionNet(nn.Module):
        """紧凑 MLP: ~1.2K 参数"""
        def __init__(self, n=N_FEAT, h1=24, h2=16):
            super().__init__()
            self.backbone = nn.Sequential(
                nn.Linear(n, h1), nn.ReLU(),
                nn.Linear(h1, h2), nn.ReLU(),
            )
            self.dir_head = nn.Linear(h2, 3)
            self.conf_head = nn.Linear(h2, 1)
        def forward(self, x):
            z = self.backbone(x)
            return self.dir_head(z), self.conf_head(z)  # conf 为 raw logits
except ImportError:
    # P2-LOW: torch 未安装 → 离线优雅跳过 (不报错、记 warning、不阻断进化).
    #   DL 盘感裁判按无模型处理 (双裁判之一 inactive, 低危, 见审计事实#7).
    torch = None
    nn = None
    F = None
    TORCH_AVAILABLE = False
    DEVICE = None
    IntuitionNet = None
    print("[提示] torch 未安装, 盘感模型离线 (DL 裁判按无模型处理; 不影响进化)")

# ═══════════════════════════════════════════════
# 数据构建 (训练: 序列遍历; 推理: 末根)
# ═══════════════════════════════════════════════
LOOKAHEAD = 12  # 12 根 H1 = 12 小时前向收益

def build_dataset(h1, h4, d1, w1, tc_dir, tc_stale, lookahead=LOOKAHEAD, thr=0.004):
    """返回 X(np,N), y_dir(np,), y_tc(np,) — 训练用"""
    c1 = h1['close'].values
    n = len(c1)
    X, yd, ytc = [], [], []
    tcsig = _enc_bias(tc_dir)
    tc_class = CLASS_UP if tcsig > 0 else (CLASS_DOWN if tcsig < 0 else CLASS_FLAT)
    for i in range(55, n - lookahead):
        f = compute_scalar_features(h1, h4, d1, w1, i, tc_dir, tc_stale)
        if f is None: continue
        fut = c1[i + lookahead]/c1[i] - 1
        if fut > thr: lab = CLASS_UP
        elif fut < -thr: lab = CLASS_DOWN
        else: lab = CLASS_FLAT
        X.append(features_to_vector(f))
        yd.append(lab)
        ytc.append(tc_class)
    return np.array(X, dtype=np.float32), np.array(yd, dtype=np.int64), np.array(ytc, dtype=np.int64)

# ═══════════════════════════════════════════════
# 优化器 (训练 / 加载 / 推理)
# ═══════════════════════════════════════════════
class DLOptimizer:
    def __init__(self):
        self.model = IntuitionNet().to(DEVICE)
        self.model.eval()

    @staticmethod
    def load():
        if not TORCH_AVAILABLE or IntuitionNet is None:
            return None
        if os.path.exists(MODEL_PATH):
            try:
                o = DLOptimizer()
                o.model.load_state_dict(torch.load(MODEL_PATH, map_location=DEVICE))
                o.model.eval()
                return o
            except Exception as e:
                print(f"  [DL] 加载模型失败: {e}")
                return None
        return None

    def save(self):
        torch.save(self.model.state_dict(), MODEL_PATH)

    # ── 推理: 接入分析器 ──
    def boost_from_raw(self, symbol, rule_bias_str, tc_consensus, tc_stale, mt5):
        """拉最新 MT5 数据 → 算特征 → 预测方向/置信度/评分加成
        rule_bias_str: 规则引擎给的偏置(BULLISH/BEARISH/SIDEWAYS), 用于计算评分加成方向
        """
        tf_map = {"H1": 16385, "H4": 16388, "D1": 16408, "W1": 32769}
        bars = {"H1": 400, "H4": 400, "D1": 300, "W1": 120}
        frames = {}
        for tn, code in tf_map.items():
            rates = mt5.copy_rates_from_pos(symbol, code, 0, bars[tn])
            if rates is None or len(rates) == 0:
                if tn == "W1":
                    continue
                raise RuntimeError(f"MT5 数据失败 {symbol} {tn}")
            fr = pd.DataFrame(rates); fr["time"] = pd.to_datetime(fr["time"], unit="s")
            frames[tn] = fr
        h1 = frames["H1"]; h4 = frames["H4"]; d1 = frames["D1"]; w1 = frames.get("W1")
        tc_dir = tc_consensus.get(symbol) if isinstance(tc_consensus, dict) else None
        i = len(h1) - 1
        f = compute_scalar_features(h1, h4, d1, w1, i, tc_dir, tc_stale)
        if f is None:
            return None, None, 0.0
        x = torch.tensor(features_to_vector(f), dtype=torch.float32).unsqueeze(0).to(DEVICE)
        with torch.no_grad():
            dlogits, conf = self.model(x)
            probs = F.softmax(dlogits, dim=1)[0].cpu().numpy()
            cls = int(np.argmax(probs))
            cval = float(torch.sigmoid(conf).cpu().numpy().reshape(-1)[0])
        dl_dir = {CLASS_DOWN: "BEARISH", CLASS_FLAT: "SIDEWAYS", CLASS_UP: "BULLISH"}[cls]
        dl_conf = float(0.5 * cval + 0.5 * float(np.max(probs)))
        # 评分加成: DL 方向与规则偏置同向→+, 反向→-, 幅度随置信度
        rule_bias = _enc_bias(rule_bias_str)
        if rule_bias == 0:
            score_adjust = 0.0
        else:
            score_adjust = (1.0 if _enc_bias(dl_dir) == rule_bias else -1.0) * dl_conf
        return dl_dir, round(dl_conf, 3), round(score_adjust, 3)

    # ── 训练: 真实 MT5 历史 ──
    def train_on_mt5(self, symbols, epochs=80, batch=128, lr=1e-3):
        import MetaTrader5 as mt5
        if not mt5.initialize():
            mt5.initialize()
        X_all, y_all, yt_all = [], [], []
        for sym in symbols:
            try:
                h1 = pd.DataFrame(mt5.copy_rates_from_pos(sym, 16385, 0, 2000))
                h4 = pd.DataFrame(mt5.copy_rates_from_pos(sym, 16388, 0, 1500))
                d1 = pd.DataFrame(mt5.copy_rates_from_pos(sym, 16408, 0, 800))
                w1 = pd.DataFrame(mt5.copy_rates_from_pos(sym, 32769, 0, 300))
                for fr in (h1, h4, d1, w1):
                    fr["time"] = pd.to_datetime(fr["time"], unit="s")
                tc_dir = None  # 训练时不用 TC 历史快照, 仅主任务
                X, yd, yt = build_dataset(h1, h4, d1, w1, tc_dir, False)
                X_all.append(X); y_all.append(yd); yt_all.append(yt)
                print(f"  [DL] {sym}: {len(X)} 样本")
            except Exception as e:
                print(f"  [DL] {sym} 跳过: {e}")
        if not X_all:
            print("  [DL] 无训练数据"); return
        X = np.concatenate(X_all); y = np.concatenate(y_all); yt = np.concatenate(yt_all)
        # 类别权重(抑制 FLAT 多数)
        cls_w = torch.tensor([1.5, 0.6, 1.5], dtype=torch.float32).to(DEVICE)
        ds = torch.utils.data.TensorDataset(
            torch.tensor(X), torch.tensor(y), torch.tensor(yt))
        dl = torch.utils.data.DataLoader(ds, batch_size=batch, shuffle=True)
        opt = torch.optim.Adam(self.model.parameters(), lr=lr)
        self.model.train()
        for ep in range(epochs):
            tot = 0; cnt = 0
            for xb, yb, ytb in dl:
                xb, yb, ytb = xb.to(DEVICE), yb.to(DEVICE), ytb.to(DEVICE)
                dlog, conf = self.model(xb)
                dir_loss = F.cross_entropy(dlog, yb, weight=cls_w)
                tc_loss = F.cross_entropy(dlog, ytb)
                conf_t = ((yb == CLASS_UP).float() + (yb == CLASS_DOWN).float()) * 0.5 + 0.25
                conf_loss = F.binary_cross_entropy_with_logits(conf.squeeze(), conf_t)
                loss = dir_loss + 0.3 * tc_loss + 0.2 * conf_loss
                opt.zero_grad(); loss.backward(); opt.step()
                tot += loss.item(); cnt += 1
            if (ep+1) % 20 == 0:
                print(f"  [DL] epoch {ep+1}/{epochs}  loss={tot/max(cnt,1):.4f}")
        self.model.eval(); self.save()
        print(f"  [DL] 训练完成, 模型保存: {MODEL_PATH} (样本={len(X)})")

# ═══════════════════════════════════════════════
# 合成数据冒烟测试 (无 MT5 也能验证可学性)
# ═══════════════════════════════════════════════
def generate_synthetic(n=2600, seed=7):
    rng = np.random.default_rng(seed)
    regime = rng.integers(0, 3, n)
    drift = np.where(regime == 2, 0.0007, np.where(regime == 0, -0.0007, 0.0))
    rets = rng.normal(0, 0.0012, n) + drift
    close = np.cumprod(1 + rets) * 100.0
    high = close * (1 + np.abs(rng.normal(0, 0.0009, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.0009, n)))
    open_ = np.roll(close, 1); open_[0] = close[0]
    time = pd.date_range('2024-01-01', periods=n, freq='1h')
    return pd.DataFrame({'time': time, 'open': open_, 'high': high, 'low': low,
                         'close': close, 'tick_volume': rng.integers(100, 1000, n)})

def run_smoke_test(epochs=40, save_path=None):
    print("=" * 60)
    print("  A.T.E. Deep Learning Optimizer — 冒烟测试 (合成数据)")
    print("=" * 60)
    h1 = generate_synthetic()
    h4 = generate_synthetic(1500, 11)
    d1 = generate_synthetic(900, 23)
    w1 = generate_synthetic(320, 31)
    # 合成 TC 老师: 70% 概率与真实前向方向一致(模拟较靠谱分析师)
    c1 = h1['close'].values
    y_true = []
    for i in range(55, len(c1) - LOOKAHEAD):
        fut = c1[i + LOOKAHEAD]/c1[i] - 1
        y_true.append(CLASS_UP if fut > 0.004 else (CLASS_DOWN if fut < -0.004 else CLASS_FLAT))
    rng = np.random.default_rng(99)
    tc_class = []
    for y in y_true:
        if rng.random() < 0.70:
            tc_class.append(y)
        else:
            tc_class.append(rng.integers(0, 3))
    # 用合成数据构造特征, 但把 TC 标签按序列对齐喂给 build_dataset 不便,
    # 这里直接复用 build_dataset 得 X/y, 再覆盖 y_tc 为合成老师
    X, y_dir, _ = build_dataset(h1, h4, d1, w1, None, False)
    y_tc = np.array(tc_class[:len(y_dir)], dtype=np.int64)
    print(f"  样本数={len(X)}  类别分布={np.bincount(y_dir)}")
    cls_w = torch.tensor([1.5, 0.6, 1.5], dtype=torch.float32).to(DEVICE)
    ds = torch.utils.data.TensorDataset(torch.tensor(X), torch.tensor(y_dir), torch.tensor(y_tc))
    dl = torch.utils.data.DataLoader(ds, batch_size=128, shuffle=True)
    trainer = DLOptimizer()
    model = trainer.model
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    model.train()
    best = 1e9
    for ep in range(epochs):
        tot = 0; cnt = 0
        for xb, yb, ytb in dl:
            xb, yb, ytb = xb.to(DEVICE), yb.to(DEVICE), ytb.to(DEVICE)
            dlog, conf = model(xb)
            dir_loss = F.cross_entropy(dlog, yb, weight=cls_w)
            tc_loss = F.cross_entropy(dlog, ytb)
            conf_t = ((yb == CLASS_UP).float() + (yb == CLASS_DOWN).float()) * 0.5 + 0.25
            conf_loss = F.binary_cross_entropy_with_logits(conf.squeeze(), conf_t)
            loss = dir_loss + 0.3 * tc_loss + 0.2 * conf_loss
            opt.zero_grad(); loss.backward(); opt.step()
            tot += loss.item(); cnt += 1
        avg = tot/max(cnt, 1)
        best = min(best, avg)
        if (ep+1) % 10 == 0:
            print(f"  epoch {ep+1}/{epochs}  loss={avg:.4f}")
    # 评估
    model.eval()
    with torch.no_grad():
        dlog, _ = model(torch.tensor(X).to(DEVICE))
        pred = dlog.argmax(1).cpu().numpy()
    acc = (pred == y_dir).mean()
    acc_updown = ((pred != CLASS_FLAT) == (y_dir != CLASS_FLAT)).mean()
    print(f"\n  结果: 总准确率={acc:.3f} (随机基线≈0.333) | 多空方向命中={acc_updown:.3f}")
    print(f"  最低loss={best:.4f}  → {'✅ 已学到盘感(胜过随机)' if acc > 0.40 else '⚠ 未明显胜过随机, 需调参'}")
    if save_path:
        torch.save(model.state_dict(), save_path)
        print(f"  模型已存: {save_path}")
    return acc

if __name__ == "__main__":
    if TORCH_AVAILABLE:
        run_smoke_test()
    else:
        print("[提示] torch 未安装, 跳过 DL 冒烟测试")
