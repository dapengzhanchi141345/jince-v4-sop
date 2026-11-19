"""
v10.4 Neural Core — LSTM-Autoencoder + ForCNN 混合模型
训练 + 回测 一体化管道

架构:
  分支A: BiLSTM(64) → 32维市场隐状态 (自监督)
  分支B: 2D CNN → 16维视觉特征 (监督)
  融合: 3任务输出 (方向/波动/置信度)
"""
import sys, os, json, warnings, math
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from collections import defaultdict
warnings.filterwarnings('ignore')

BASE = r"E:\GoldstrategyEngine"
DATA_DIR = os.path.join(BASE, "data")
os.makedirs(DATA_DIR, exist_ok=True)

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Using: {device}")

# ═══════════════════════════════════════════════
# Part 1: 特征工程
# ═══════════════════════════════════════════════
def build_features(h1_df, h4_df, d1_df):
    """构建训练特征矩阵"""
    h1 = h1_df.copy()
    h4 = h4_df.copy()
    d1 = d1_df.copy()
    
    # H1基础特征
    h1['returns'] = h1['close'].pct_change()
    h1['log_ret'] = np.log(h1['close'] / h1['close'].shift(1))
    h1['hl_range'] = (h1['high'] - h1['low']) / h1['close']
    h1['body'] = abs(h1['close'] - h1['open']) / (h1['high'] - h1['low'] + 1e-10)
    h1['upper_w'] = (h1['high'] - np.maximum(h1['close'], h1['open'])) / (h1['high'] - h1['low'] + 1e-10)
    h1['lower_w'] = (np.minimum(h1['close'], h1['open']) - h1['low']) / (h1['high'] - h1['low'] + 1e-10)
    
    # 动量
    for p in [5, 10, 20]:
        h1[f'roc_{p}'] = h1['close'].pct_change(p)
        h1[f'vol_{p}'] = h1['hl_range'].rolling(p).mean()
        h1[f'vol_ratio_{p}'] = h1['hl_range'] / (h1['hl_range'].rolling(p).mean() + 1e-10)
    
    # EMA交叉
    for s in [9, 14, 21, 50]:
        h1[f'ema_{s}'] = h1['close'].ewm(span=s).mean()
        h1[f'ema_dist_{s}'] = (h1['close'] - h1[f'ema_{s}']) / h1['close']
    
    # 成交量
    h1['vol_norm'] = h1['tick_volume'] / (h1['tick_volume'].rolling(50).mean() + 1e-10)
    
    # 时间特征
    h1['hour_sin'] = np.sin(2 * np.pi * pd.to_datetime(h1['time']).dt.hour / 24)
    h1['hour_cos'] = np.cos(2 * np.pi * pd.to_datetime(h1['time']).dt.hour / 24)
    
    h1 = h1.fillna(0).replace([np.inf, -np.inf], 0)
    
    # ===== 标签构建 (未来12小时的预测目标) =====
    fut_lookahead = 12  # 12小时
    
    # 方向标签: 3类 (UP=1, DOWN=-1, FLAT=0)
    h1['fwd_return'] = h1['close'].shift(-fut_lookahead) / h1['close'] - 1
    h1['direction'] = 0  # FLAT
    h1.loc[h1['fwd_return'] > 0.005, 'direction'] = 1   # UP
    h1.loc[h1['fwd_return'] < -0.005, 'direction'] = -1  # DOWN
    
    # 波动标签
    h1['fwd_vol'] = h1['hl_range'].shift(-fut_lookahead).rolling(5).mean()
    h1['vol_target'] = h1['fwd_vol'] / (h1['hl_range'].rolling(5).mean() + 1e-10)
    h1['vol_target'] = h1['vol_target'].clip(0.1, 5.0)
    
    return h1

def build_sequence_data(h1_feat, seq_len=120):
    """构建序列数据集"""
    feat_cols = [c for c in h1_feat.columns if c not in ['time','open','high','low','close',
                'tick_volume','spread','real_volume','returns','fwd_return','direction','vol_target','fwd_vol']]
    
    X_seqs, y_dir, y_vol = [], [], []
    X_images = []  # ForCNN输入
    
    for i in range(seq_len, len(h1_feat) - 12):
        seq = h1_feat[feat_cols].iloc[i-seq_len:i].values
        X_seqs.append(seq)
        y_dir.append(h1_feat['direction'].iloc[i] + 1)  # 0,1,2
        y_vol.append(h1_feat['vol_target'].iloc[i])
        
        # ForCNN: 最近24根K线→6×4灰度图 (使用单一特征, reshape 24点)
        img_data = h1_feat['hl_range'].iloc[i-24:i].values  # 24个值
        img = (img_data - img_data.min()) / (img_data.max() - img_data.min() + 1e-10)
        X_images.append(img.reshape(6, 4))
    
    return np.array(X_seqs), np.array(y_dir), np.array(X_images)


# ═══════════════════════════════════════════════
# Part 2: 模型定义
# ═══════════════════════════════════════════════

class LSTMEncoder(nn.Module):
    """LSTM-Autoencoder 编码器 (精简版)"""
    def __init__(self, input_dim, hidden_dim=20, latent_dim=8):
        super().__init__()
        self.lstm = nn.LSTM(input_dim, hidden_dim, batch_first=True)
        self.encoder = nn.Linear(hidden_dim, latent_dim)
        self.decoder = nn.Linear(latent_dim, input_dim)
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.latent_dim = latent_dim
    
    def forward(self, x):
        lstm_out, _ = self.lstm(x)
        last = lstm_out[:, -1, :]  # (batch, 20)
        latent = self.encoder(last)  # (batch, 8)
        recon = self.decoder(latent).unsqueeze(1).repeat(1, 120, 1)  # (batch, 120, input_dim)
        return latent, recon

class ForCNN(nn.Module):
    """ForCNN: 时序→灰度图→CNN (精简版)"""
    def __init__(self):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv2d(1, 8, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.AdaptiveAvgPool2d((1, 1)),
        )
        self.fc = nn.Linear(8, 4)
    
    def forward(self, x):
        conv_out = self.conv(x).view(x.size(0), -1)
        return self.fc(conv_out)

class GoldNet(nn.Module):
    """混合模型 (精简版)"""
    def __init__(self, input_dim, num_classes=3):
        super().__init__()
        self.lstm_enc = LSTMEncoder(input_dim)
        self.forcnn = ForCNN()
        self.fusion = nn.Sequential(
            nn.Linear(8 + 4, 16),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(16, num_classes),
        )
        self.conf_head = nn.Sequential(
            nn.Linear(8 + 4, 8),
            nn.ReLU(),
            nn.Linear(8, 1),
            nn.Sigmoid(),
        )
    
    def forward(self, seq, img):
        latent, recon = self.lstm_enc(seq)
        vis_feat = self.forcnn(img)
        combined = torch.cat([latent, vis_feat], dim=1)
        dir_out = self.fusion(combined)
        conf_out = self.conf_head(combined)
        return dir_out, conf_out, recon


# ═══════════════════════════════════════════════
# Part 3: 训练
# ═══════════════════════════════════════════════
def train_model(h1_df, h4_df, d1_df, epochs=50, batch_size=64):
    print("\n=== 特征工程 ===")
    h1_feat = build_features(h1_df, h4_df, d1_df)
    
    print("构建序列数据集...")
    X_seq, y_dir, X_img = build_sequence_data(h1_feat)
    
    # 分割: 前75%训练, 后25%验证
    split = int(len(X_seq) * 0.75)
    train_idx = list(range(0, split))
    val_idx = list(range(split, len(X_seq)))
    
    # 标准化
    seq_mean = X_seq[train_idx].mean(axis=(0, 1))
    seq_std = X_seq[train_idx].std(axis=(0, 1)) + 1e-10
    X_seq = (X_seq - seq_mean) / seq_std
    
    # 创建数据加载器
    train_ds = TensorDataset(
        torch.FloatTensor(X_seq[train_idx]),
        torch.FloatTensor(X_img[train_idx]).unsqueeze(1),
        torch.LongTensor(y_dir[train_idx]),
    )
    val_ds = TensorDataset(
        torch.FloatTensor(X_seq[val_idx]),
        torch.FloatTensor(X_img[val_idx]).unsqueeze(1),
        torch.LongTensor(y_dir[val_idx]),
    )
    
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=batch_size)
    
    # 初始化模型
    input_dim = X_seq.shape[2]
    model = GoldNet(input_dim).to(device)
    
    criterion_cls = nn.CrossEntropyLoss()
    criterion_recon = nn.MSELoss()
    optimizer = optim.AdamW(model.parameters(), lr=3e-3, weight_decay=1e-4)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    
    print(f"模型参数: {sum(p.numel() for p in model.parameters()):,}")
    print(f"训练集: {len(train_idx)} 验证集: {len(val_idx)}")
    print(f"\n=== 训练 {epochs} epochs ===")
    
    best_val_loss = float('inf')
    history = {'train_loss': [], 'val_loss': [], 'val_acc': []}
    
    for epoch in range(epochs):
        model.train()
        train_loss = 0
        for seq, img, dir_lbl in train_loader:
            seq, img = seq.to(device), img.to(device)
            dir_lbl = dir_lbl.to(device)
            
            optimizer.zero_grad()
            dir_out, conf_out, recon = model(seq, img)
            
            loss_dir = criterion_cls(dir_out, dir_lbl)
            loss_recon = criterion_recon(recon, seq)
            loss = loss_dir * 0.7 + loss_recon * 0.3
            
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            
            train_loss += loss.item()
        
        # 验证
        model.eval()
        val_loss = 0
        correct = 0
        total = 0
        with torch.no_grad():
            for seq, img, dir_lbl in val_loader:
                seq, img = seq.to(device), img.to(device)
                dir_lbl = dir_lbl.to(device)
                dir_out, conf_out, recon = model(seq, img)
                
                loss_dir = criterion_cls(dir_out, dir_lbl)
                loss_recon = criterion_recon(recon, seq)
                loss = loss_dir * 0.7 + loss_recon * 0.3
                val_loss += loss.item()
                
                _, predicted = torch.max(dir_out, 1)
                total += dir_lbl.size(0)
                correct += (predicted == dir_lbl).sum().item()
        
        scheduler.step()
        
        avg_train = train_loss / len(train_loader)
        avg_val = val_loss / len(val_loader)
        acc = correct / total * 100
        
        history['train_loss'].append(avg_train)
        history['val_loss'].append(avg_val)
        history['val_acc'].append(acc)
        
        if (epoch + 1) % 5 == 0 or epoch == 0:
            print(f"  Epoch {epoch+1:2d}/{epochs} | Train: {avg_train:.4f} | Val: {avg_val:.4f} | Acc: {acc:.1f}%")
        
        if avg_val < best_val_loss:
            best_val_loss = avg_val
            torch.save(model.state_dict(), os.path.join(DATA_DIR, "goldnet_best.pt"))
    
    # 加载最优模型
    model.load_state_dict(torch.load(os.path.join(DATA_DIR, "goldnet_best.pt")))
    print(f"\n训练完成. 最优验证损失: {best_val_loss:.4f}, 验证精度: {max(history['val_acc']):.1f}%")
    
    # 保存标准化参数
    norm_params = {'mean': seq_mean.tolist(), 'std': seq_std.tolist()}
    with open(os.path.join(DATA_DIR, "goldnet_norm.json"), "w") as f:
        json.dump(norm_params, f)
    
    return model, h1_feat, seq_mean, seq_std, history


# ═══════════════════════════════════════════════
# Part 4: NN集成回测
# ═══════════════════════════════════════════════
def backtest_with_nn(h1_df, h4_df, d1_df, model, seq_mean, seq_std,
                     initial=10000, lot=0.01, conf_threshold=0.3):
    """v10.4 + NN 集成回测"""
    h1_feat = build_features(h1_df, h4_df, d1_df)
    
    feat_cols = [c for c in h1_feat.columns if c not in ['time','open','high','low','close',
                'tick_volume','spread','real_volume','returns','fwd_return','direction','vol_target','fwd_vol']]
    
    h1c = h1_df['close'].values
    h1h = h1_df['high'].values
    h1l = h1_df['low'].values
    ht = h1_df['time'].values
    
    # 指标
    def _ema(vals, period):
        r = np.full(len(vals), np.nan)
        r[period-1] = np.mean(vals[:period])
        a = 2/(period+1)
        for i in range(period, len(vals)):
            r[i] = vals[i]*a + r[i-1]*(1-a)
        return r
    
    def _atr(h, l, p=14):
        tr = np.maximum(h[1:]-l[1:], np.maximum(np.abs(h[1:]-np.roll(h1c,1)[1:]), np.abs(l[1:]-np.roll(h1c,1)[1:])))
        r = np.full(len(h), np.nan)
        r[p] = np.mean(tr[:p])
        a = 1/p
        for i in range(p+1, len(h)):
            r[i] = tr[i-1]*a + r[i-1]*(1-a)
        return pd.Series(r).ffill().fillna(np.mean(tr[:p])).values
    
    def _adx(h, l, c, p=14):
        if len(c) < p*2: return np.zeros(len(c))
        tr = np.maximum(h[1:]-l[1:], np.maximum(np.abs(h[1:]-c[:-1]), np.abs(l[1:]-c[:-1])))
        u, d = h[1:]-h[:-1], l[:-1]-l[1:]
        pdi = 100*pd.Series(np.where((u>d)&(u>0),u,0)).ewm(span=p).mean()/(pd.Series(tr).ewm(span=p).mean()+1e-10)
        mdi = 100*pd.Series(np.where((d>u)&(d>0),d,0)).ewm(span=p).mean()/(pd.Series(tr).ewm(span=p).mean()+1e-10)
        dx = 100*np.abs(pdi-mdi)/(pdi+mdi+1e-10)
        result = pd.Series(dx).ewm(span=p).mean().values
        return np.concatenate([np.zeros(len(c)-len(result)), result])
    
    h4c = h4_df['close'].values
    e14 = _ema(h1c, 14)
    e28 = _ema(h1c, 28)
    adx_v = _adx(h1h, h1l, h1c)
    atr_v = _atr(h1h, h1l)
    h4adx = _adx(h4_df['high'].values, h4_df['low'].values, h4c)
    
    # D1
    dc = d1_df['close'].values
    de9 = _ema(dc, 9)
    de21 = _ema(dc, 21)
    
    model.eval()
    trades = []
    pos = None
    bal = float(initial)
    eq = [bal]
    daily_t = 0
    last_d = None
    consec_l = 0
    cool_until = None
    prog_sl = None
    nn_correct = 0
    nn_total = 0
    
    for i in range(140, len(h1_df)):  # Need 120 seq + 20 warmup
        bt = pd.Timestamp(ht[i])
        price = h1c[i]
        bh = h1h[i]
        bl = h1l[i]
        
        cd = bt.date()
        if last_d != cd:
            daily_t = 0
            last_d = cd
        
        if cool_until and bt < cool_until:
            eq.append(bal)
            continue
        
        # ─── 持仓管理 ───
        if pos:
            esl = prog_sl if prog_sl is not None else pos['sl']
            hit_sl = hit_tp = False
            reason = ''
            if pos['side'] == 1:
                if bl <= min(esl, pos['sl']): hit_sl, reason = True, 'SL'
                elif bh >= pos['tp']: hit_tp, reason = True, 'TP'
            else:
                if bh >= max(esl, pos['sl']): hit_sl, reason = True, 'SL'
                elif bl <= pos['tp']: hit_tp, reason = True, 'TP'
            
            if hit_sl or hit_tp:
                ep = pos['sl'] if hit_sl else pos['tp']
                profit = (ep - pos['entry']) * pos['side'] * lot * 100
                
                trades.append({
                    'open_time': pos['ot'].strftime('%Y-%m-%d %H:%M'),
                    'close_time': bt.strftime('%Y-%m-%d %H:%M'),
                    'direction': 'BUY' if pos['side']==1 else 'SELL',
                    'entry': round(pos['entry'],2), 'exit': round(ep,2),
                    'profit': round(profit,2),
                    'result': 'WIN' if profit>0 else 'LOSS',
                    'reason': reason, 'regime': pos.get('regime',''),
                    'nn_conf': round(pos.get('nn_conf',0),3),
                })
                bal += profit
                if profit < 0:
                    consec_l += 1
                    if consec_l >= 5: cool_until = bt + timedelta(hours=24)
                    elif consec_l >= 3: cool_until = bt + timedelta(hours=4)
                    elif consec_l >= 2: cool_until = bt + timedelta(minutes=30)
                else: consec_l = 0
                pos = None; prog_sl = None
                eq.append(bal)
                continue
            else:
                # 渐进止盈
                r_ = abs(pos['entry'] - pos['sl'])
                if r_ > 0 and prog_sl is None:
                    d_ = (price - pos['entry']) * pos['side']
                    mult = d_ / r_
                    if mult > 2.0: prog_sl = pos['entry'] + 1.5 * r_ * pos['side']
                    elif mult > 1.0: prog_sl = pos['entry'] + 0.5 * r_ * pos['side']
                    elif mult > 0.5: prog_sl = pos['entry']
                eq.append(bal)
                continue
        
        # ─── 新信号 ───
        if daily_t >= 8: eq.append(bal); continue
        if not (15 <= bt.hour < 24): eq.append(bal); continue
        if np.isnan(adx_v[i]) or adx_v[i] < 22: eq.append(bal); continue
        
        # 市场状态
        h4i = min(i//4, len(h4c)-1)
        hadx = h4adx[max(0,h4i)]
        regime = 'trend'
        if hadx < 20 and adx_v[i] < 20: regime = 'ranging'
        if hadx > 35: regime = 'strong_trend'
        atr_hist = atr_v[max(0,i-30):i+1]
        if len(atr_hist) > 10 and atr_v[i] > np.mean(atr_hist)*1.8: regime = 'volatile'
        if regime == 'volatile': eq.append(bal); continue
        
        if np.isnan(e14[i]) or np.isnan(e28[i]): eq.append(bal); continue
        trend = 'UP' if e14[i] > e28[i] else 'DOWN'
        
        # D1方向
        d1_idx = min(i//24, len(dc)-1)
        if d1_idx >= 21 and not np.isnan(de9[d1_idx]) and not np.isnan(de21[d1_idx]):
            d1_dir = 'UP' if de9[d1_idx] > de21[d1_idx] else 'DOWN'
        else: d1_dir = trend
        
        # ═══ NN 推理 ═══
        with torch.no_grad():
            seq = h1_feat[feat_cols].iloc[i-120:i].values
            seq_norm = (seq - seq_mean) / seq_std
            seq_t = torch.FloatTensor(seq_norm).unsqueeze(0).to(device)
            
            img_raw = h1_feat['hl_range'].iloc[i-24:i].values  # single feature, 24 points
            img_min = img_raw.min()
            img_max = img_raw.max()
            img_norm = (img_raw - img_min) / (img_max - img_min + 1e-10)
            img_t = torch.FloatTensor(img_norm.reshape(1, 1, 6, 4)).to(device)  # add channel dim
            
            dir_out, conf_out, _ = model(seq_t, img_t)
            
            nn_conf = conf_out.item()
            _, nn_dir = torch.max(dir_out, 1)
            nn_dir_label = ['DOWN','FLAT','UP'][nn_dir.item()]
        
        nn_total += 1
        
        # NN方向与规则方向一致时才考虑入场
        rule_buy = d1_dir == 'UP'
        rule_sell = d1_dir == 'DOWN'
        
        nn_buy = nn_dir_label == 'UP' and nn_conf > conf_threshold
        nn_sell = nn_dir_label == 'DOWN' and nn_conf > conf_threshold
        
        if nn_buy and nn_dir_label == d1_dir:
            nn_correct += 1
        
        direction = None
        if rule_buy and nn_buy:
            direction = 'BUY'
        elif rule_sell and nn_sell:
            direction = 'SELL'
        
        if not direction:
            eq.append(bal)
            continue
        
        # SL/TP
        sl_mult, rr_mult = 1.5, 2.5
        if regime == 'ranging':
            sl_mult = min(sl_mult*0.7, 0.8)
            rr_mult = max(rr_mult*0.8, 1.5)
        elif regime == 'strong_trend':
            sl_mult = max(sl_mult*1.2, 1.0)
            rr_mult *= 1.2
        
        # NN置信度调整仓位和SL
        adj_lot = lot * (0.5 + nn_conf)  # conf 0.3→0.8x, 0.6→1.1x, 0.9→1.4x
        adj_lot = min(0.03, adj_lot)  # max 3x standard
        
        sl = price - atr_v[i] * sl_mult if direction == 'BUY' else price + atr_v[i] * sl_mult
        tp = price + (price - sl) * rr_mult if direction == 'BUY' else price - (sl - price) * rr_mult
        
        pos = {
            'side': 1 if direction=='BUY' else -1,
            'entry': price, 'sl': sl, 'tp': tp,
            'ot': bt, 'regime': regime,
            'nn_conf': nn_conf,
        }
        daily_t += 1
        eq.append(bal)
    
    if pos:
        profit = (h1c[-1]-pos['entry'])*pos['side']*lot*100
        trades.append({
            'open_time': pos['ot'].strftime('%Y-%m-%d %H:%M'),
            'close_time': pd.Timestamp(ht[-1]).strftime('%Y-%m-%d %H:%M'),
            'direction': 'BUY' if pos['side']==1 else 'SELL',
            'entry': round(pos['entry'],2), 'exit': round(h1c[-1],2),
            'profit': round(profit,2), 'result': 'WIN' if profit>0 else 'LOSS',
            'reason': '回测结束', 'regime': pos.get('regime',''),
            'nn_conf': round(pos.get('nn_conf',0),3),
        })
        bal += profit
    
    return trades, bal, np.array(eq), nn_correct, nn_total


# ═══════════════════════════════════════════════
# Part 5: 报告
# ═══════════════════════════════════════════════
def gen_report(trades, balance, equity, initial, nn_acc=None):
    closed = [t for t in trades if t.get('result','') != 'OPEN']
    if not closed: return {'error':'无交易'}
    
    wins = [t for t in closed if t['profit']>0]
    losses = [t for t in closed if t['profit']<0]
    total = sum(t['profit'] for t in closed)
    wr = len(wins)/len(closed)*100
    
    avg_w = np.mean([t['profit'] for t in wins]) if wins else 0
    avg_l = abs(np.mean([t['profit'] for t in losses])) if losses else 0
    gp = sum(t['profit'] for t in wins) if wins else 0
    gl = abs(sum(t['profit'] for t in losses)) if losses else 0
    pf = gp/gl if gl>0 else float('inf')
    
    peak = equity[0]; max_dd_pct = 0
    for e in equity:
        if e > peak: peak = e
        dd_pct = (peak-e)/peak*100
        if dd_pct > max_dd_pct: max_dd_pct = dd_pct
    
    rets = np.diff(equity)/(equity[:-1]+1e-10)
    sharpe = np.mean(rets)/np.std(rets)*np.sqrt(365*24) if len(rets)>1 and np.std(rets)>0 else 0
    ret_pct = total/initial*100
    calmar = ret_pct/max_dd_pct if max_dd_pct>0 else 0
    
    cw=cl=mw=ml=0
    for t in closed:
        if t['profit']>0: cw+=1; cl=0
        else: cl+=1; cw=0
        mw=max(mw,cw); ml=max(ml,cl)
    
    rs = defaultdict(lambda: {'t':0,'w':0,'p':0})
    for t in closed:
        r = t.get('regime','?').strip()
        rs[r]['t'] += 1; rs[r]['p'] += t['profit']
        if t['profit']>0: rs[r]['w'] += 1
    
    ms = defaultdict(lambda: {'t':0,'w':0,'p':0})
    for t in closed:
        m = t['close_time'][:7]
        ms[m]['t'] += 1; ms[m]['p'] += t['profit']
        if t['profit']>0: ms[m]['w'] += 1
    
    # NN置信度分层分析
    conf_buckets = {'low(<0.3)':[],'med(0.3-0.6)':[],'high(>0.6)':[]}
    for t in closed:
        c = t.get('nn_conf', 0)
        if c < 0.3: conf_buckets['low(<0.3)'].append(t['profit'])
        elif c < 0.6: conf_buckets['med(0.3-0.6)'].append(t['profit'])
        else: conf_buckets['high(>0.6)'].append(t['profit'])
    
    return {
        'period': f"{closed[0]['open_time'][:10]} ~ {closed[-1]['close_time'][:10]}",
        'total_trades': len(closed), 'wins': len(wins), 'losses': len(losses),
        'win_rate': round(wr,1), 'total_pnl': round(total,2),
        'avg_win': round(avg_w,2), 'avg_loss': round(avg_l,2),
        'profit_factor': round(pf,2), 'sharpe_ratio': round(sharpe,2),
        'calmar_ratio': round(calmar,2),
        'max_drawdown_pct': round(max_dd_pct,2),
        'max_consec_wins': mw, 'max_consec_losses': ml,
        'final_balance': round(initial+total,2), 'return_pct': round(ret_pct,2),
        'nn_accuracy': round(nn_acc*100,1) if nn_acc else 0,
        'regime_stats': {k:{'trades':v['t'],'wr':round(v['w']/v['t']*100,1) if v['t']>0 else 0,
                           'pnl':round(v['p'],2)} for k,v in rs.items()},
        'monthly_stats': {k:{'trades':v['t'],'wr':round(v['w']/v['t']*100,1) if v['t']>0 else 0,
                            'pnl':round(v['p'],2)} for k,v in sorted(ms.items())},
        'conf_breakdown': {k:{'count':len(v),'avg_pnl':round(np.mean(v),2) if v else 0,
                              'total':round(sum(v),2)} for k,v in conf_buckets.items()},
    }


# ═══ MAIN ═══
if __name__ == '__main__':
    print('='*65)
    print('  v10.4 Neural Core — 训练 + 回测')
    print('='*65)
    
    # 1. 加载数据
    h1 = pd.read_csv(os.path.join(DATA_DIR,'XAUUSD_H1.csv'), parse_dates=['time'])
    h4 = pd.read_csv(os.path.join(DATA_DIR,'XAUUSD_H4.csv'), parse_dates=['time'])
    d1 = pd.read_csv(os.path.join(DATA_DIR,'XAUUSD_D1.csv'), parse_dates=['time'])
    print(f'\n数据: H1={len(h1)} H4={len(h4)} D1={len(d1)}')
    
    # 2. 训练
    model, h1_feat, seq_mean, seq_std, history = train_model(h1, h4, d1, epochs=50)
    
    # 3. 回测
    print('\n=== NN集成回测 ===')
    trades, bal, eq, nn_correct, nn_total = backtest_with_nn(
        h1, h4, d1, model, seq_mean, seq_std)
    nn_acc = nn_correct/max(nn_total,1)
    closed_trades = [t for t in trades if t.get('result','') != 'OPEN']
    print(f'完成: {len(closed_trades)} 笔, 余额 ${bal:.2f}')
    print(f'NN方向预测精度: {nn_acc*100:.1f}% ({nn_correct}/{nn_total})')
    
    # 4. 报告
    r = gen_report(trades, bal, eq, 10000, nn_acc)
    
    print('\n'+'='*65)
    print('  v10.4 + Neural Core  一年实盘回测报告')
    print(f'  期间: {r.get("period","N/A")}  |  本金: $10,000')
    print('='*65)
    print(f'{"指标":<25} {"值":<20}')
    print('-'*45)
    
    for k,v in [
        ('总交易数',f"{r.get('total_trades',0)} 笔"),
        ('盈利',f"{r.get('wins',0)} 笔"), ('亏损',f"{r.get('losses',0)} 笔"),
        ('胜率',f"{r.get('win_rate',0)}%"),
        ('总盈亏',f"${r.get('total_pnl',0):.2f}"),
        ('收益率',f"{r.get('return_pct',0):+.2f}%"),
        ('平均盈利',f"${r.get('avg_win',0):.2f}"),
        ('平均亏损',f"${r.get('avg_loss',0):.2f}"),
        ('盈亏比(PF)',f"{r.get('profit_factor',0):.2f}"),
        ('夏普比率',f"{r.get('sharpe_ratio',0):.2f}"),
        ('卡尔玛比率',f"{r.get('calmar_ratio',0):.2f}"),
        ('最大回撤',f"{r.get('max_drawdown_pct',0):.2f}%"),
        ('最大连赢',f"{r.get('max_consec_wins',0)} 笔"),
        ('最大连亏',f"{r.get('max_consec_losses',0)} 笔"),
        ('NN方向精度',f"{r.get('nn_accuracy',0)}%"),
        ('期末余额',f"${r.get('final_balance',0):.2f}"),
    ]: print(f'{k:<25} {v:<20}')
    
    print('\n'+'-'*65)
    print('■ NN置信度分层分析')
    print('- '*30)
    print(f'{"层级":<15} {"笔数":<8} {"平均盈亏":<12} {"累计":<10}')
    for k,v in r.get('conf_breakdown',{}).items():
        print(f'{k:<15} {v["count"]:<8} ${v["avg_pnl"]:<9.2f} ${v["total"]:<8.2f}')
    
    print('\n'+'-'*65)
    print('■ 市场状态分解')
    print('- '*30)
    print(f'{"状态":<15} {"笔数":<8} {"胜率":<8} {"PnL":<10}')
    for k,v in r.get('regime_stats',{}).items():
        print(f'{k:<15} {v["trades"]:<8} {v["wr"]:<7.1f}% ${v["pnl"]:<8.2f}')
    
    print('\n'+'-'*65)
    print('■ 月度分解')
    print('- '*30)
    print(f'{"月份":<10} {"笔数":<8} {"胜率":<8} {"PnL":<10}')
    for k,v in list(r.get('monthly_stats',{}).items()):
        print(f'{k:<10} {v["trades"]:<8} {v["wr"]:<7.1f}% ${v["pnl"]:<8.2f}')
    
    # 评估
    pnl = r.get('total_pnl',0)
    pf_v = r.get('profit_factor',0)
    sh = r.get('sharpe_ratio',0)
    dd = r.get('max_drawdown_pct',0)
    wr_v = r.get('win_rate',0)
    tn = r.get('total_trades',0)
    nn_acc_v = r.get('nn_accuracy',0)
    
    print('\n'+'='*65)
    print('▶ 评估结论:')
    if tn == 0: print('  ❌ 零交易')
    elif pnl > 0 and pf_v > 1.5 and sh > 0.5:
        print('  ✅ Neural Core 集成策略盈利, 风险调整后收益良好')
    elif pnl > 0:
        print('  ✅ 盈利策略')
    else: print('  ❌ 当期亏损')
    print(f'  • 交易频率: {tn}/年 = {tn/365:.2f} 笔/天')
    print(f'  • NN方向预测: {nn_acc_v}% (vs 随机33.3%)')
    print(f'  • 胜率 {wr_v}% {"- 良好" if wr_v>35 else "- 偏低" if wr_v>20 else "- 需改进"}')
    print(f'  • 盈亏比 {pf_v} {"- 优秀" if pf_v>2 else "- 良好" if pf_v>1.5 else "- 亏损"}')
    print(f'  • 夏普比率 {sh} {"- 优秀" if sh>1.5 else "- 良好" if sh>0.5 else "- 需改进"}')
    print(f'  • 最大回撤 {dd}% {"- 可控" if dd<15 else "- 偏高"}')
    print('='*65)
    
    # 保存
    out = os.path.join(DATA_DIR,'backtest_nn_report.json')
    with open(out,'w',encoding='utf-8') as f:
        json.dump(r,f,indent=2,ensure_ascii=False)
    print(f'\n报告已保存: {out}')
    if trades:
        pd.DataFrame(trades).to_csv(os.path.join(DATA_DIR,'backtest_nn_trades.csv'),index=False)
        print('交易明细已保存')
    
    # 保存训练历史
    hist_out = os.path.join(DATA_DIR,'training_history.json')
    with open(hist_out,'w') as f:
        json.dump(history,f,indent=2)
    print(f'训练历史已保存: {hist_out}')
