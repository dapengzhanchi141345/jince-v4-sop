# run_trader.py — 金策宗师团 · 自主交易循环 (猎场司扫盘 + 监军司看护)
#
# 一个进程同时做两件事, 真正"时刻在线交易":
#   1. 猎场司扫盘: 对每个品种 scan_symbol → build_signal(ADX/结构/自适应暂停)
#      → 多周期共振过滤(H4/D1) → audit_and_execute(审度司VETO + LIVE硬开关)
#   2. 监军司看护: 对每个既有持仓 supervise_once → 保本/追踪/平仓
#
# 安全铁律 (金策宗师团 v4.0):
#   - 所有下单仍过审度司 VETO; 绝不放松止损
#   - 已有持仓的品种, 猎场司不再开新仓 (交给监军司看护, 防重复加仓)
#   - LIVE 需 --live 显式开启; 默认 DRY-RUN 只报告不开仓不改单
#   - 日风险 ≤3% 由审度司硬卡; 自适应暂停闸门在信号层拦截
#
# 用法:
#   python run_trader.py                  # 默认 DRY-RUN: 看护+扫盘只报告
#   python run_trader.py --live          # 真执行: 经审度司审计后开/平/改
#   python run_trader.py --live --loop   # 实时自主交易 (每 --interval 秒一轮)
#   python run_trader.py --selftest      # 离线单测 (猎场司 + 监军司)

import sys
# 强制 stdout/stderr 为 UTF-8 (errors='replace' 兜底), 防止被外部重定向
# (watchdog.ps1 的 PowerShell RedirectStandardOutput 在中文 Windows 下用 GBK)
# 时, 代码打印 emoji(🔴/🦬) 触发 UnicodeEncodeError 把启动进化整段打断.
# 此入口同时覆盖主 live 与异步进化子进程(--evolve-only), 一处修复全链路.
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass
import time
import json
import os
import traceback
import subprocess
import guardian_executor as ge
# 本系统固定 magic number (P0-HIGH-3): 与 guardian_executor.SYSTEM_MAGIC 同源,
# 所有开/平/改单统一打此标签, 供 drift_monitor 按魔法数过滤本系统成交,
# 避免账户里其它手动/其它 EA 的成交污染实盘漂移统计。两处须保持一致。
from guardian_executor import SYSTEM_MAGIC
import position_supervisor as ps
import market_scanner as mh
import continuous_evolution_v2 as ce
import drift_monitor as dm
import live_bridge as lb
import edge_tracker as et
import ctypes

# ══ 同源 live 桥接开关 ══
# 默认开启 (用户已选"同源接入 live"): 让 60043976 的 live 交易走与回测同源的
# advanced_strategies + risk_lot 引擎。设环境变量 GOLD_BRIDGE=0 可退回 legacy 引擎。
BRIDGE_MODE = os.environ.get("GOLD_BRIDGE", "1") != "0"
# [2026-09-24 CIO 全面接管] 多智能体决策层(事件总监→研究→交易→风控一票否决)。
# 在审度司 VETO 之**前**先过一遍 CIO; CIO 否决/事件HALT → 该单拒开。
# 失败开放: CIO 任何异常/缺模块 → 全部放行, 绝不阻断现有审度司链。
# GOLD_CIO=0 可关。
CIO_MODE = os.environ.get("GOLD_CIO", "1") != "0"
BRIDGE_KEEP = []            # init_bridge() 填充
BRIDGE_RISK_PCT = 2.5      # [2026-08-21 P5] 单笔风险上限: 1.5%→2.5% (允许贵金属/Crypto开仓)
BRIDGE_MAX_POS = 25         # [2026-08-18 D2] 全局在仓硬上限: 止血, 防负edge裸奔84仓; 配合板块配额分散
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")


# 自进化重优化: 每软重置周期跑一次 Walk-Forward (真实 MT5 回测, 只读不下单)
EVOLVE_ROUNDS = 30
# 启动即触发一次有界自进化(消除"干等4h"痛点, 真正"时刻保持进化状态")
STARTUP_EVOLVE_ROUNDS = 20
STARTUP_EVOLVE_MAX_SEC_PER_SYM = 120   # 单品种上限, 整体最坏 7×120≈14min
# 异步软重置进化: 单品种预算(比启动更宽松, 因不阻塞交易; 整体最坏 7×180≈21min)
ASYNC_EVOLVE_BUDGET_SEC_PER_SYM = 180

# [2026-08-22 P3-2] 蒙特卡洛压力测试轮次计数 (每20轮约40分钟评估一次)
_mc_counter = [0]


def _crash_hook(exc_type, exc_value, exc_tb):
    """崩溃钩子: 未捕获异常落盘, 不静默丢失 (守护进程韧性)."""
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        log = os.path.join(here, 'logs', 'trader_crash.log')
        os.makedirs(os.path.dirname(log), exist_ok=True)
        with open(log, 'a', encoding='utf-8') as f:
            f.write(time.strftime('%Y-%m-%d %H:%M:%S') + " CRASH\n")
            f.write(''.join(traceback.format_exception(exc_type, exc_value, exc_tb)))
            f.write("\n")
    except Exception:
        pass
    sys.__excepthook__(exc_type, exc_value, exc_tb)


def _is_pid_alive(pid):
    """跨平台进程存活探测 (Windows 用 GetProcessVersion, 令牌无关, 与 OpenProcess 陷阱无关).

    [2026-07-11 修复] 原实现仅以 OpenProcess 是否成功判存活 —— 在 Windows 上有
    已知陷阱: 进程已退出(exit)但内核对象尚未被回收(zombie)时, OpenProcess 仍返回
    有效句柄 → 误判"存活", 导致陈旧 live.pid 指向已死进程时新实例拒绝启动(重复开仓
    防护反噬). 正确语义必须用 GetExitCodeProcess: 仅当退出码 == STILL_ACTIVE(259)
    才视为仍在运行; 返回其它值(含 0/已退出)一律判死, 触发陈旧 pidfile 回收.

    [2026-08-15 强化] 改用 GetProcessVersion(pid) 作为主判据: 不依赖任何句柄/令牌,
    进程存在即返回非零版本号, 不存在返回 0. 彻底规避 OpenProcess(0x0400) 在 pythonw/
    HKCU Run 启动场景下因访问令牌差异返回 NULL(h==0) 而误判"已死"的陷阱 —— 该陷阱会
    让败者 live 实例错误回收存活持有者的锁并抢占, 造成双 live/双开仓死机. 令牌无关、
    绝对可靠. 仅在 GetProcessVersion 不可用时回退 os.kill(pid,0).
    """
    if pid is None or int(pid) <= 0:
        return False
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        ver = kernel32.GetProcessVersion(int(pid))
        if ver != 0:
            return True
        return False
    except Exception:
        try:
            os.kill(int(pid), 0)
            return True
        except Exception:
            return False


def _live_pidfile_path():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, 'data', 'live.pid')


# [2026-09-03 修复] 初始化互斥体句柄为 None, 确保 atexit 时可安全关闭
_LIVE_MUTEX_HANDLE = None


def _create_live_mutex():
    """内核级命名互斥体(全局单实例 live). 返回 True=获得; False=已有实例(应退出).

    用 Windows CreateMutexW(Global\\) 原子创建 —— 文件系统层之下的内核对象,
    不可被 TOCTOU/竞态/多次启动绕过. 这是 pidfile 锁之外的第二道、更彻底的单实例保障,
    专门解决"手动多次启动/看门狗竞态导致双 live 进程双开仓"问题.

    [关键] ctypes 默认不捕获 LastError, 需 SetLastError(0) 复位后再读, 否则读到陈旧
    错误码(常 183)导致永远误判"已被占用"而退出.
    """
    try:
        kernel32 = ctypes.windll.kernel32
        # [2026-08-15 修复] 必须显式声明 argtypes/restype, 否则 ctypes 默认 c_int 解析
        # HANDLE(64位)与宽字符串名会错乱, 导致 GetLastError 误报 183(已被占用) ->
        # 单例锁永远误判"已有 live" -> live 启动即退出 -> 看门狗反复拉起 -> 累积多实例.
        kernel32.SetLastError.restype = ctypes.c_uint
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        ERROR_ALREADY_EXISTS = 183
        kernel32.SetLastError(0)
        # [2026-08-16 加固] 优先 Global\\ 跨会话(真防双开), 失败回退会话级, 再失败软降级.
        h = None
        err = 0
        for _name in ("Global\\GoldstrategyLiveTrader", "GoldstrategyLiveTrader"):
            kernel32.SetLastError(0)
            h = kernel32.CreateMutexW(None, 0, _name)
            err = kernel32.GetLastError()
            if h:
                break
        if not h:
            return True   # 创建失败(无权限等): 软降级放行, 单实例职责交回文件锁, 绝不阻断交易
        if err == ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(h)
            return False  # 已有 live 实例
        # 成功获得: 持有句柄至进程退出(存模块全局, 防 GC 误关句柄导致互斥体被销毁)
        global _LIVE_MUTEX_HANDLE
        _LIVE_MUTEX_HANDLE = h
        return True
    except Exception:
        # [2026-08-15 修复] ctypes 异常时软降级放行(绝不阻断交易); 单实例职责交回文件锁.
        return True


def _live_mutex_held_by_other():
    """只读探测: 是否已存在别的 live 持有内核互斥体. 用 OpenMutex(不创建、不持有句柄),
    零副作用, 供运维核查真实单实例状态. 返回 True=确有别的 live 持有(单实例正常);
    False=无人持有或探测失败(含权限不足)."""
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.OpenMutexW.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.c_wchar_p]
        kernel32.OpenMutexW.restype = ctypes.c_void_p
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        MUTEX_ALL_ACCESS = 0x1F0000
        for _name in ("Global\\GoldstrategyLiveTrader", "GoldstrategyLiveTrader"):
            kernel32.SetLastError(0)
            h = kernel32.OpenMutexW(MUTEX_ALL_ACCESS, False, _name)
            if h:
                kernel32.CloseHandle(h)
                return True
        return False
    except Exception:
        return False


def _live_lock_acquire():
    """单例锁 (仅 --live 调用): 若已有 live 实例在跑, 本进程立即退出, 杜绝重复开仓/双重下单。
    本函数是 data/live.pid 的唯一写入方; watchdog 只读取, 避免"自写自身 PID"冲突。
    
    [2026-09-03 修复] 子进程(--evolve-only)不获取互斥体, 避免循环死锁.
    """
    # [2026-09-03] 子进程不获取互斥体, 直接返回成功
    if '--evolve-only' in sys.argv:
        return True
    
    # [2026-08-16 加固] 内核级互斥体作为第一道、最彻底的单实例闸(Global\\ 跨会话, 真防双开).
    # 先抢内核互斥体: 已被其它 live 持有 -> 立即退出, 连 pidfile 都不必读.
    if not _create_live_mutex():
        print("[单例锁] 内核互斥体已被其它 live 实例持有, 为避免重复开仓/双重下单, 本进程退出。")
        return False
    try:
        pidfile = _live_pidfile_path()
        if os.path.exists(pidfile):
            old = None
            try:
                with open(pidfile) as f:
                    old = int(f.read().strip())
            except Exception:
                old = None
            if old and old != os.getpid() and _is_pid_alive(old):
                print(f"[单例锁] 检测到已有 live 实例 (PID {old}) 运行中, "
                      f"为避免重复开仓/双重下单, 本进程退出。")
                return False
            # 陈旧/无效 pidfile -> 回收
            # [2026-08-21 修复] os.remove 被 WorkBuddy shim 的 safe-delete 劫持
            # (沙箱无回收站 → FAIL_CLOSED), 陈旧 pidfile 删不掉 → 新实例 O_EXCL
            # 创建锁失败 → watchdog 反复拉起又反复退出(死循环). 改用 Win32
            # DeleteFileW 绕过 shim, 与 watchdog.py 的 _force_delete 同款.
            try:
                ctypes.windll.kernel32.DeleteFileW(pidfile)
            except Exception:
                try:
                    os.remove(pidfile)
                except Exception:
                    pass
        # 原子创建锁文件, 杜绝 TOCTOU 竞态 (双进程同毫秒启动互相绕过 exists 检查)
        try:
            fd = os.open(pidfile, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
        except FileExistsError:
            try:
                old = int(open(pidfile).read().strip())
            except Exception:
                old = None
            print(f"[单例锁] 锁文件已被实例 PID {old} 占用, 为避免重复开仓/双重下单, 本进程退出。")
            return False
        import atexit
        def _release():
            try:
                # [2026-09-03 修复] 先关闭内核互斥体句柄, 防止循环死锁
                global _LIVE_MUTEX_HANDLE
                if _LIVE_MUTEX_HANDLE:
                    try:
                        ctypes.windll.kernel32.CloseHandle(_LIVE_MUTEX_HANDLE)
                    except Exception:
                        pass
                    _LIVE_MUTEX_HANDLE = None
                # 再删除 pidfile
                if os.path.exists(pidfile):
                    with open(pidfile) as f:
                        if f.read().strip() == str(os.getpid()):
                            try:
                                ctypes.windll.kernel32.DeleteFileW(pidfile)
                            except Exception:
                                try:
                                    os.remove(pidfile)
                                except Exception:
                                    pass
            except Exception:
                pass
        atexit.register(_release)
        return True
    except Exception as e:
        print(f"[单例锁] 异常({e}), 放行(不阻断交易)。")
        return True


def _beat():
    """写心跳文件 data/live.heartbeat (Unix 时间戳)。
    watchdog 用它与 PID 命名空间无关地判断 live 是否存活 (避免 MSYS2/Windows PID 错配)。"""
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, 'data', 'live.heartbeat'), 'w') as f:
            f.write(str(time.time()))
    except Exception:
        pass


def _build(live):
    """构建 共享 guardian + 猎场司 + 监军司 三联体 (同一 MT5 连接/审计器)."""
    _rpt = 0.025 if BRIDGE_MODE else 0.02     # [2026-08-21 P5] 单笔风险上限: 1.5%→2.5% (允许贵金属/Crypto开仓)
    # [2026-08-20 P0] 日累计风险上限: 1.5%→3%
    _dr = 0.03 if BRIDGE_MODE else 0.05
    guardian = ge.GuardianExecutor(
        auto_confirm=live, max_risk_per_trade=_rpt, max_daily_risk=_dr)
    if not guardian.connect():
        return None
    if live:
        # 真仓防护 (金策宗师团安全铁律): 仅当 server 名含 'demo'(不区分大小写)
        # 或显式 GOLD_ALLOW_REAL=1 才开启实盘交易; 防止误连真仓造成实损。
        # 注: MT5 trade_mode==0 在部分 broker 的 demo 上也会报 0(=REAL),
        # 故不以 trade_mode 判真/伪, 而以 server 名为准。
        _server = ""
        try:
            _ai = guardian.mt5.account_info()
            _server = (_ai.server or "") if _ai else ""
        except Exception:
            _server = ""
        _allow_real = os.environ.get("GOLD_ALLOW_REAL", "") == "1"
        if _allow_real or "demo" in _server.lower():
            ge.LIVE_TRADING_ENABLED = True
            print(f"[{time.strftime('%H:%M:%S')}] [真仓防护] server='{_server}' "
                  f"通过校验, 开启 LIVE_TRADING")
        else:
            print(f"[{time.strftime('%H:%M:%S')}] ⛔ [真仓防护] server='{_server}' "
                  f"非 demo 且未设 GOLD_ALLOW_REAL=1, 拒绝开启实盘交易, 进程退出。")
            return None
    if BRIDGE_MODE:
        global BRIDGE_KEEP
        BRIDGE_KEEP = lb.init_bridge(DATA_DIR)
        # [2026-09-04 修复] V4 白名单品种强制并入扫描宇宙:
        #   KEEP-32 源自 8/24 旧回测缓存 _ub_partial.json, XAUUSD(今日进化
        #   fit=100/PnL+$29934)/CADJPY(实盘PF5.02)/AUDCHF(实盘PF1.38) 当时被标
        #   CUT/COLLECT → 不在 KEEP-32 → 从未被扫描 → 0 交易. 现把实盘 edge
        #   已放行的 V4 白名单品种(et.is_symbol_allowed=True)并入扫描列表,
        #   让验证赢家真正可交易; 仍受 scan_symbol 内 V4/edge/ADX/V5 多重闸约束.
        try:
            import edge_tracker as _et
            _merged = set(BRIDGE_KEEP)
            for _s in lb.V4_SYMBOL_GATE:
                if _s in _merged:
                    continue
                try:
                    if _et.is_symbol_allowed(_s):
                        _merged.add(_s)
                except Exception:
                    pass
            BRIDGE_KEEP = sorted(_merged)
            print(f"[{time.strftime('%H:%M:%S')}] [同源桥接] KEEP宇宙并入V4白名单, "
                  f"可交易 {len(BRIDGE_KEEP)} 个 (含 XAUUSD/CADJPY/AUDCHF 实盘edge验证赢家)")
        except Exception as _e:
            print(f"[同源桥接] V4并入失败(用原KEEP-32): {_e}")
        print(f"[{time.strftime('%H:%M:%S')}] [同源桥接] 已接入 KEEP-32 验证宇宙, "
              f"可交易 {len(BRIDGE_KEEP)} 个 (回测 PF≥1.15 且 n≥30 验证, "
              f"单笔{BRIDGE_RISK_PCT}%/总险5%/{BRIDGE_MAX_POS}仓, 轮询扫描)")
    # 逐品种独立参数: 加载全部品种最优策略(未覆盖品种回退全局 best)
    strategies = ps.load_all_best_strategies()
    hunter = mh.MarketHunter(strategies=strategies, guardian=guardian)
    # 激活已验证增强 (仅运行时开启, 不替审度司 VETO / ADX<20 硬禁 / 缠论 gate):
    #   - 缠论中枢 ZG/ZD 动态止损 (替代固定 ATR SL, 结构破位离场)
    #   - RF 质量门禁: 2026-07-10 回测证伪负优化(BTC/ETH无门禁PF1.40 vs 门禁0.43~1.11), 已关闭
    mh.CHANLUN_SL_OVERRIDE = True
    mh.RF_QUALITY_GATE = False  # 2026-07-10 回测证伪: 门禁在BTC/ETH是负优化, 关闭让有edge提案出单
    # ── 全品种收集模式 (策金尊升级, 默认关闭) ──
    # 用户把 symbol_universe.DATA_COLLECTION_MODE=True 置位后, 自动把
    # UNIVERSE(39品种) 合并进 ce.SYMBOL_CONFIG → 猎场司扫盘覆盖全品种;
    # market_scanner 的 EDGE GATE 同步放开, 允许无进化优势品种也开仓(守双铁律/
    # 风控), 用于"先全品种放开 → 收集实盘数据 → 按盈利筛选决定保留哪些".
    import symbol_universe as _su
    if _su.DATA_COLLECTION_MODE:
        _su.load_universe_into_ce()
        print(f"[{time.strftime('%H:%M:%S')}] 全品种收集模式已载入宇宙 "
              f"({len(ce.SYMBOL_CONFIG)} 品种)")
    supervisor = ps.PositionSupervisor(auto_confirm=live, dry_run=not live)
    supervisor.guardian = guardian       # 共享同一审计/日志/连接
    supervisor.mt5 = guardian.mt5
    return guardian, hunter, supervisor


def _launch_async_evolution():
    """拉起独立子进程跑 Walk-Forward 自进化(只读回测不下单).

    子进程自己连 MT5(独立 session, 与主 live 进程隔离), 写 evolution_state.json 后退出.
    主循环继续轮询交易, 不阻塞; 新 state 由 _maybe_hotload_evolved 自动热加载.
    """
    try:
        py = sys.executable
        script = os.path.abspath(__file__)
        cmd = [py, script, '--evolve-only', f'--rounds={EVOLVE_ROUNDS}',
               f'--budget={ASYNC_EVOLVE_BUDGET_SEC_PER_SYM}']
        proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW)
        print(f"[{time.strftime('%H:%M:%S')}] 自进化子进程已启动 PID={proc.pid} "
              f"(后台跑, 主循环不阻塞)")
    except Exception as e:
        print(f"[自进化] 异步拉起失败(本轮跳过, 下个周期重试): {e}")


def _state_mtime():
    """evolution_state.json 最后修改时间(检测进化子进程是否写出新结果)."""
    p = os.path.join(ce.EVOLVE_DIR, 'evolution_state.json')
    try:
        return os.path.getmtime(p)
    except OSError:
        return 0.0


def _maybe_hotload_evolved(hunter, mtime_holder):
    """进化子进程写完 state 后, 主循环自动热加载新最优策略(本轮即生效)."""
    m = _state_mtime()
    if m > mtime_holder[0]:
        try:
            hunter.strategies = ps.load_all_best_strategies()
            print(f"[{time.strftime('%H:%M:%S')}] 检测到新进化结果, "
                  f"已热加载最新最优策略(本轮即生效)")
            mtime_holder[0] = m
        except Exception as e:
            print(f"[热加载] 失败(沿用旧策略): {e}")
    return mtime_holder[0]


def _cycle(guardian, hunter, supervisor, live):
    lines = []
    # [2026-08-26 修复] 止损冷却: 扫描近6h成交, 发现 SL 止损平仓 → 记录
    # 品种级冷却(4h) + 配对冷却(6h), 防止"止损→立即重开→再止损"循环
    # (8/25 AUDJPY 单日20次, XAGUSD 配对5连亏 -20.52).
    try:
        import datetime as _dtt
        import live_bridge as _lb
        import pairs_trader as _pt
        _now_ts = time.time()
        _from_ts = _now_ts - 6 * 3600
        _dl = guardian.mt5.history_deals_get(int(_from_ts), int(_now_ts))
        if _dl:
            for _d in _dl:
                if getattr(_d, 'entry', 0) != 1:
                    continue
                _cm = str(getattr(_d, 'comment', '') or '')
                if getattr(_d, 'profit', 0) < 0 and 'sl' in _cm.lower():
                    _sym = _d.symbol
                    # 品种级冷却 (所有策略)
                    _lb._sym_stop_now(_sym)
                    # 配对冷却 (仅PAIR腿)
                    if 'PAIR' in _cm:
                        for _pa, _pb, *_rest in _pt.DEFAULT_PAIRS:
                            if _sym in (_pa, _pb):
                                _lb._pair_stop_now(f"{_pa}/{_pb}")
                                lines.append(f"  [配对冷却] {_pa}/{_pb} 止损, "
                                             f"6h内禁止重开")
                                break
    except Exception:
        pass
    # [2026-08-22 P3-2] 蒙特卡洛压力测试: 每 20 轮 (约40分钟) 评估一次组合风险,
    #   仅预警不拦截 (历史成交含门控修复前亏损, 硬拦会停摆). 输出到日志供人工参考.
    try:
        _mc_counter[0] += 1
        if _mc_counter[0] >= 20:
            _mc_counter[0] = 0
            import monte_carlo as _mc
            _eq_now = float(guardian.mt5.account_info().equity or 500.0)
            # [2026-08-23 优化] 窗口自适应: 门控修复后(8/20起)交易已转正,
            # 7天窗口被历史灾难数据(8/18: 787笔-347)污染 → 持续误报FAIL.
            # 改为近3天(修复后有效交易)评估; 近3天样本不足(<10笔)时说明
            # 当前为质量优先稀疏交易, 直接SKIP不回退(回退7天会被历史污染).
            import datetime as _dt
            _d3 = _dt.datetime.now() - _dt.timedelta(days=3)
            _dl3 = guardian.mt5.history_deals_get(int(_d3.timestamp()),
                                                  int(_dt.datetime.now().timestamp()))
            _n3 = len([x for x in (_dl3 or []) if getattr(x, 'entry', 0) == 1])
            if _n3 < 10:
                lines.append(f"  [蒙特卡洛] 近3天仅{_n3}笔(质量优先), 样本不足跳过压力测试")
            else:
                _r = _mc.run_strategy_mc(guardian.mt5, days=3,
                                         initial_equity=_eq_now, n_paths=200)
                if _r.get('verdict') in ('FAIL', 'WARN'):
                    lines.append(f"  [蒙特卡洛-{_r['verdict']}(3天{_r.get('n_trades',0)}笔)] {_r['reason']}")
                else:
                    lines.append(f"  [蒙特卡洛-PASS(3天{_r.get('n_trades',0)}笔)] 组合风险可控")
    except Exception as ex:
        lines.append(f"  [蒙特卡洛] 评估异常(跳过): {ex}")
    # —— 监军司看护既有持仓 ——
    # 看护异常隔离: 即便看护任一品种出错, 也绝不阻塞后续扫盘与新开仓
    try:
        sres = supervisor.supervise_once()
    except Exception as ex:
        sres = None
        lines.append(f"[监军司] 看护异常(已跳过, 不影响扫盘): {ex}")
    lines.append(supervisor.report(sres) if sres else "[监军司] 无持仓/看护跳过, 待命")
    # [2026-08-18 D6] 主动清负 edge 旧仓: 平掉实盘 pf<1.0 品种的已有持仓, 加速收敛.
    #   与 D1 门控同源(edge_tracker.is_symbol_allowed), 但作用于"已有持仓"而非"新开".
    #   每轮 refresh_if_stale(5min节流) + 遍历持仓, 负 edge 品种立即平仓释放风险.
    try:
        et.refresh_if_stale(guardian.mt5)
        _pos_d6 = guardian.mt5.positions_get() or []
        _closed_d6 = 0
        for _p in _pos_d6:
            if not et.is_symbol_allowed(_p.symbol):
                _r = guardian.close_position(_p.ticket)
                if isinstance(_r, dict) and _r.get("closed"):
                    _closed_d6 += 1
        if _closed_d6:
            lines.append(f"  [D6] 主动清负edge旧仓: 平掉 {_closed_d6} 个 (实盘pf<1.0品种)")
    except Exception as ex:
        lines.append(f"  [D6] 清负edge旧仓异常(跳过): {ex}")
    # —— 猎场司扫盘开新仓 ——
    positions = guardian.mt5.positions_get() or []
    existing = {p.symbol for p in positions}
    # 现有持仓方向表 (供组合相关性风控 DRY-RUN 评估; 默认 PORTFOLIO_CORR_CHECK
    # 关闭时, 该信息仅在开启后才生效, 不破任何铁律/不改行为)
    open_dirs = {p.symbol: ('BUY' if p.type == guardian.mt5.POSITION_TYPE_BUY
                           else 'SELL') for p in positions}
    if BRIDGE_MODE:
        equity = guardian._equity()
        # [2026-08-28 P3] 账户回撤熔断: 更新峰值, 回撤>10%降半仓/15%暂停
        try:
            guardian.auditor.set_peak_equity(equity)
            _dd_scale = guardian.auditor.drawdown_scale()
            if _dd_scale < 1.0:
                lines.append(f"  [回撤熔断] 回撤={guardian.auditor.drawdown_pct()*100:.0f}% "
                             f"仓位缩放={_dd_scale:.1f} "
                             f"({'暂停新开' if _dd_scale == 0 else '降半仓'})")
        except Exception:
            _dd_scale = 1.0
        # ── P0-3 组合波动率目标: 高波动期自动降单笔风险 → 降回撤/破产风险 ──
        _record_equity(equity)
        vscaler = vol_target_scaler()
        # ── 新闻事件风险闸: 高影响事件窗口自动降手数/暂停新开仓, 保护本金优先 ──
        esc = event_risk_scaler()
        evt_lv = _event_risk_level()
        eff_risk = BRIDGE_RISK_PCT * vscaler * esc * _dd_scale
        if esc <= 0.0:
            scans = []
            lines.append(f"  [新闻闸] 等级={evt_lv} 暂停新开仓(仅看护既有持仓) "
                         f"vscaler={vscaler:.2f}")
            src_tag = "同源桥接"
        else:
            scans = lb.scan_all(guardian, BRIDGE_KEEP, existing, open_dirs,
                                equity=equity, risk_pct=eff_risk,
                                max_pos=BRIDGE_MAX_POS, data_dir=DATA_DIR,
                                class_map=lb.CLASS_STRATEGY_MAP)
            src_tag = "同源桥接"
            lines.append(f"  [波动率目标] scaler={vscaler:.2f} 新闻闸={evt_lv}({esc:.2f}) "
                         f"实际单笔风险={eff_risk:.3f}% (基准 {BRIDGE_RISK_PCT}%)")
    else:
        scans = hunter.scan_all(existing_symbols=existing, open_dirs=open_dirs)
        src_tag = "猎场司"
    # [2026-08-26 修复] 配对联动: 同一 pair_ref 的提案先全部审计, 任一腿被拒
    # 则整对不下 (防止只开单腿变裸空). 先收集配对对, 非配对照常逐个执行.
    _pair_audits = {}   # pair_ref -> [(p, ...)]
    _order = []         # 执行顺序: [(p, is_pair)]
    for sc in scans:
        sym = sc['symbol']
        if sc['proposal'] is None:
            lines.append(f"  [{src_tag}] {sym}: SKIP ({sc['reason']})")
            continue
        p = sc['proposal']
        pr = p.get('pair_ref')
        if pr:
            _pair_audits.setdefault(pr, []).append(p)
        _order.append((p, pr is not None))

    # ── [2026-09-24 CIO 全面接管] 多智能体决策闸门 ──
    # 审度司 VETO 之前先过 CIO(事件总监→研究→交易→风控一票否决)。
    # CIO 否决/事件HALT → 该单从本轮执行中剔除(下游 audit_and_execute 也不会再看到)。
    # 失败开放: CIO 异常/未启用 → 放行全部, 绝不阻断现有审度司链。
    _all_cand = [sc['proposal'] for sc in scans if sc['proposal'] is not None]
    _cio_blocked, _cio_global, _cio_lines = _cio_gate(_all_cand)
    lines.extend(_cio_lines)
    if _cio_global:
        lines.append("  [CIO] ⛔ 全局拦截: 本轮全部新开仓暂停(仅看护既有持仓)")
        _order = []
        _pair_audits = {}
    elif _cio_blocked:
        _order = [(p, is_pair) for (p, is_pair) in _order
                  if p.get('symbol') not in _cio_blocked]
        for pr, plist in list(_pair_audits.items()):
            _pair_audits[pr] = [p for p in plist if p.get('symbol') not in _cio_blocked]
            if not _pair_audits[pr]:
                _pair_audits.pop(pr)
        lines.append(f"  [CIO] 剔除 {_cio_blocked & set(p.get('symbol') for p, _ in _order)} "
                     f"共{len(_cio_blocked)}个被否决品种")

    # ── [2026-10-25 data_health] 品种级数据健康硬闸 (修复单② 洞②, 真接进挂单链) ──
    # red / data_unreliable → 该品种新腿 0 开 (品种级, 不置全市场 halt); yellow → 仓位 ×0.5。
    _dh_red, _dh_yellow, _dh_lines = data_health_gate(_all_cand)
    lines.extend(_dh_lines)
    if _dh_red:
        _dh_syms = _dh_red
        _order = [(p, is_pair) for (p, is_pair) in _order if p.get('symbol') not in _dh_syms]
        for pr, plist in list(_pair_audits.items()):
            _pair_audits[pr] = [p for p in plist if p.get('symbol') not in _dh_syms]
            if not _pair_audits[pr]:
                _pair_audits.pop(pr)
    if _dh_yellow:
        # yellow 品种仓位再 ×0.5 (只缩新单手数, 不碰既有持仓)
        for p, _ispair in _order:
            if p.get('symbol') in _dh_yellow and 'lot' in p:
                try:
                    p['lot'] = max(float(p.get('lot', 0.0)) * 0.5, 0.0)
                except Exception:
                    pass

    # ── [2026-10-25 daily_loss_cap] 账户级日内亏损上限 1.5% 硬闸 (v2.0 钦定, @chief re-scope 取"真桥") ──
    # breached / data_unreliable → 本轮全部新腿 0 开 (账户级日闸, 既有持仓照管不撤单)。
    _dl_block, _dl_lines = daily_loss_cap_gate(_all_cand)
    lines.extend(_dl_lines)
    if _dl_block:
        _order = []
        _pair_audits = {}

    # ── [2026-10-26 retire_freeze] RETIRE 冻结闸读方 hook (@chief 裁(a) 主动退役, L5 销账锚) ──
    # 双源读(gate 直读 + risk_state 读-合并): scope_symbols 命中(非 exclude) → 该品种新腿 0 开(品种级)。
    # 挂在 daily_loss_cap 段后, 跟币系冻结桥/data_health 同向收紧; 不撤既有持仓(存量 0), 只拦新开。
    _rf_blocked, _rf_lines = retire_freeze_gate(_all_cand)
    lines.extend(_rf_lines)
    if _rf_blocked:
        _order = [(p, is_pair) for (p, is_pair) in _order if p.get('symbol') not in _rf_blocked]
        for pr, plist in list(_pair_audits.items()):
            _pair_audits[pr] = [p for p in plist if p.get('symbol') not in _rf_blocked]
            if not _pair_audits[pr]:
                _pair_audits.pop(pr)

    # ── [2026-08-28 P5] 长线趋势策略 (D1唐奇安突破, XAU/ETH/NAS/US500) ──
    # 与日内系统独立: 每轮扫描D1信号, 开仓需经审度司, 出场按反向突破/超时.
    # 长线仓用 LT 前缀 comment 标记, 不与日内仓冲突.
    try:
        import longterm_trader as _lt
        _lt_scans = _lt.scan_longterm(guardian.mt5, equity)
        for _act, _obj, _sym, *_rest in _lt_scans:
            if _act == "EXIT":
                # 长线出场: 直接平仓 (反向突破=趋势结束)
                try:
                    _r = guardian.close_position(int(_obj))
                    lines.append(f"  [长线] EXIT {_sym}: {_rest[0] if _rest else ''} "
                                 f"closed={_r.get('closed')}")
                except Exception as _ex:
                    lines.append(f"  [长线] EXIT {_sym} 异常: {_ex}")
            elif _act == "OPEN":
                _pp = _obj
                if live and ge.LIVE_TRADING_ENABLED:
                    try:
                        _res = guardian.audit_and_execute(_pp)
                        lines.append(f"  [长线] OPEN {_sym} {_pp['direction']} "
                                     f"{_pp['lot']} → {_res.get('decision')} "
                                     f"({_rest[0] if _rest else ''})")
                    except Exception as _ex:
                        lines.append(f"  [长线] OPEN {_sym} 异常: {_ex}")
                else:
                    lines.append(f"  [长线] OPEN {_sym} {_pp['direction']} "
                                 f"{_pp['lot']} → DRY-RUN")
    except Exception as _ex:
        lines.append(f"  [长线] 扫描异常: {_ex}")

    # 配对对: 先纯审计(不下单), 全 PASS 才逐个执行 (防半对裸单)
    _pair_pass = {}
    for pr, plist in _pair_audits.items():
        _all_pass = True
        _tmp_res = []
        if live and ge.LIVE_TRADING_ENABLED:
            _eq_tmp = guardian._equity()
            for p in plist:
                try:
                    _dec, _reasons = guardian.auditor.audit(p, _eq_tmp)
                    _tmp_res.append((p, {'decision': _dec, 'note': '配对审计',
                                         'reasons': _reasons}))
                    if _dec != 'PASS':
                        _all_pass = False
                except Exception as ex:
                    _tmp_res.append((p, {'decision': 'VETO',
                                         'note': f'审计异常: {ex}', 'reasons': []}))
                    _all_pass = False
            # 全 PASS → 逐个执行 (audit_and_execute 会再次审计并下单)
            if _all_pass:
                _tmp_res = []
                for p in plist:
                    try:
                        res = guardian.audit_and_execute(p)
                        _tmp_res.append((p, res))
                    except Exception as ex:
                        _tmp_res.append((p, {'decision': 'VETO',
                                             'note': f'执行异常: {ex}',
                                             'reasons': []}))
        else:
            for p in plist:
                _tmp_res.append((p, {'decision': 'DRY', 'note': 'DRY-RUN 提案',
                                     'reasons': []}))
        _pair_pass[pr] = _all_pass
        for p, res in _tmp_res:
            dec = res.get('decision')
            note = res.get('note', '')
            rstr = '; '.join(res.get('reasons', []))
            _tag = '✅配对' if _all_pass and dec in ('PASS', 'DRY') else '⛔配对拒'
            lines.append(f"  [{src_tag}] {p['symbol']} {p['direction']} {p['lot']} "
                         f"→ {dec} ({_tag}) reasons=[{rstr}]")
    # 非配对: 照常逐个执行
    for p, is_pair in _order:
        if is_pair:
            continue
        sym = p['symbol']
        if live and ge.LIVE_TRADING_ENABLED:
            try:
                res = guardian.audit_and_execute(p)
                dec = res.get('decision')
                note = res.get('note', '')
                reasons = res.get('reasons', [])
                rstr = '; '.join(reasons) if reasons else ''
                lines.append(f"  [{src_tag}] {sym} {p['direction']} {p['lot']} "
                             f"→ {dec} ({note}) reasons=[{rstr}]")
            except Exception as ex:
                lines.append(f"  [{src_tag}] {sym} {p['direction']} {p['lot']} "
                             f"→ 执行异常(已跳过该品种): {ex}")
        else:
            lines.append(f"  [{src_tag}] {sym} {p['direction']} {p['lot']} "
                         f"{p.get('strategy','')} sl={p.get('sl_pts')}pip "
                         f"→ DRY-RUN 提案")
    return "\n".join(lines)


def _run_drift_once():
    """漂移监控只读检查一次 —— 仅报告, 绝不交易/改仓/回滚。

    异常被吞掉, 不影响主交易循环。RED 时打显眼告警, 供 CIO 决策。
    """
    try:
        if not dm.DRIFT_MONITOR_ENABLED:
            print(f"[{time.strftime('%H:%M:%S')}] [漂移监控] 已禁用(DRIFT_MONITOR_ENABLED=False)")
            return
        res = dm.run_drift_check(days=7)   # [2026-08-18-A] 漂移改滚动窗口: 30天→7天, 避免历史负edge欠账永久压RED
        if res.get('red_alarm'):
            print(f"[{time.strftime('%H:%M:%S')}] 🔴 [漂移监控-告警] "
                  f"{json.dumps(res, ensure_ascii=False)}")
        else:
            print(f"[{time.strftime('%H:%M:%S')}] {dm.format_log(res)}")
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] [漂移监控] 运行异常(跳过, 不影响交易): {e}")


# ══ P0-3 组合波动率目标 (volatility targeting) ══
# 在固定 6% 日险上限之上, 叠加"组合波动率目标"自适应层:
#   高波动市况(账户权益实现波动率 > 年化目标) → 自动降单笔风险/手数 → 降回撤
#   低波动市况                                    → 适度增配        → 提升资本效率
# 实现: 滚动记录每轮账户权益, 估计近期实现波动率(年化), 与 target_ann 比 → 缩放因子
EQ_HISTORY_FILE = os.path.join(DATA_DIR, 'continuous_evolution', 'equity_history.json')
_VOL_MAX_POINTS = 30
_VOL_TARGET_ANN = 0.20        # 目标年化波动率 20% (常见 CTA/量化基金区间)
_VOL_MIN_SCALER = 0.35        # 最保守: 高波动期单笔风险降至 35%
_VOL_MAX_SCALER = 1.5         # 最激进: 低波动期可增配至 150%


def _record_equity(equity):
    """追加当前账户净值到滚动历史(近 _VOL_MAX_POINTS 点), 供波动率目标."""
    try:
        hist = []
        if os.path.exists(EQ_HISTORY_FILE):
            with open(EQ_HISTORY_FILE, 'r', encoding='utf-8') as f:
                hist = json.load(f)
        hist.append({'t': time.time(), 'eq': float(equity)})
        if len(hist) > _VOL_MAX_POINTS:
            hist = hist[-_VOL_MAX_POINTS:]
        os.makedirs(os.path.dirname(EQ_HISTORY_FILE), exist_ok=True)
        with open(EQ_HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(hist, f)
    except Exception:
        pass


def vol_target_scaler(target_ann=_VOL_TARGET_ANN,
                      min_s=_VOL_MIN_SCALER, max_s=_VOL_MAX_SCALER):
    """基于近期权益实现波动率(年化)动态调整风险缩放因子.

    返回 float ∈ [min_s, max_s]; 样本不足(<8点)时返回 1.0 (满额, 不阻碍起步).
    任何异常都回退 1.0, 绝不阻断交易循环."""
    try:
        if not os.path.exists(EQ_HISTORY_FILE):
            return 1.0
        with open(EQ_HISTORY_FILE, 'r', encoding='utf-8') as f:
            hist = json.load(f)
        eqs = [h['eq'] for h in hist if h.get('eq', 0) > 0]
        if len(eqs) < 8:
            return 1.0
        rets = [(eqs[i] - eqs[i - 1]) / eqs[i - 1]
                for i in range(1, len(eqs)) if eqs[i - 1] > 0]
        if len(rets) < 4:
            return 1.0
        import statistics
        sd = statistics.pstdev(rets)
        if sd <= 0:
            return 1.0
        # 每轮间隔≈120s, 日内高频: sqrt(288)≈17 近似日频 252 的日内等效,
        # 经验 ×1.5 补偿短窗口对波动的低估.
        ann = sd * (288 ** 0.5) * 1.5
        if ann <= 0:
            return 1.0
        scaler = target_ann / ann
        return max(min_s, min(max_s, scaler))
    except Exception:
        return 1.0


# ══ 新闻事件风险联动 (news-event risk gate) ══
# 读 data/event_risk.json (由「金策新闻事件监控」自动化写入).
#   level=LOW/MED  → 正常
#   level=HIGH     → new_entry_scale(默认0.3) 缩放新开仓手数, 不破既有持仓
#   level=HALT     → halt_new_entries=True, 完全暂停新开仓(仅看护既有持仓)
# 任何异常/文件缺失 → 返回 1.0 (满额, 绝不阻断交易).
EVENT_RISK_FILE = os.path.join(DATA_DIR, 'event_risk.json')
_EVENT_FRESH_SEC = 8 * 3600   # event_risk.json 超过 8h 视为过期 → 回退满额


def event_risk_scaler():
    """读事件风险文件, 返回新开仓缩放因子 ∈ [0.0, 1.0]."""
    try:
        if not os.path.exists(EVENT_RISK_FILE):
            # [2026-09-03 P0] 监控文件缺失=监控断供, 不应裸奔满额; 保守降手数
            return 0.5
        with open(EVENT_RISK_FILE, 'r', encoding='utf-8') as f:
            st = json.load(f)
        upd = st.get('updated')
        if upd:
            try:
                age = time.time() - float(upd)
                if age > _EVENT_FRESH_SEC:
                    # [2026-08-22 修复] 文件过期不应直接放行 —— 事件列表可能仍
                    # 含未来24h内的高影响事件 (如昨夜生成的今晨CPI/FOMC预告).
                    # 改为: 扫描事件列表, 有活跃事件按等级降手数, 无事件才放行.
                    events = st.get('events') or []
                    now = time.time()
                    worst = 1.0
                    for ev in events:
                        impact = str(ev.get('impact', '')).lower()
                        et = float(ev.get('time', 0) or 0)
                        # 只考虑 未来24h内 或 刚过1h内 的活跃事件 (已过时的忽略)
                        if -3600 <= (et - now) <= 24 * 3600:
                            if impact == 'high':
                                worst = min(worst, 0.5)
                            elif impact == 'medium':
                                worst = min(worst, 0.7)
                    if worst < 1.0:
                        return worst
                    # [2026-09-03 P0] 过期且无活跃事件=监控断供, 保守降手数(非裸奔满额)
                    return 0.5
            except Exception:
                pass
        if st.get('halt_new_entries'):
            return 0.0
        s = float(st.get('new_entry_scale', 1.0))
        # ── 增强(2026-08-15): 监控判级偏宽松('持续尾部风险'常被归 MED)时,
        #    直接扫描事件列表——任何 impact=='high' 的活跃事件(未过期且未超前瞻24h)
        #    强制降到 ELEVATED=0.5, 不依赖 monitor 是否把它标到 'HIGH' 级。
        #    覆盖"霍尔木兹/伊朗升级"这类 high-impact 但未归 HIGH 的缺口, 保护本金优先。 ──
        events = st.get('events') or []
        if s >= 1.0 and events:
            now = time.time()
            for ev in events:
                if str(ev.get('impact', '')).lower() == 'high':
                    et = float(ev.get('time', 0) or 0)
                    if et <= now + 24 * 3600:   # 当前/前瞻24h内均保守降手数
                        s = min(s, 0.5)
                        break
        return max(0.0, min(1.0, s))
    except Exception:
        return 1.0


def _event_risk_level():
    """读出事件等级字符串(供日志), 异常回退 'LOW'.

    增强: 若事件列表中存在 impact=='high' 的活跃事件(监控判级偏宽松未归 HIGH),
    返回 'ELEVATED' 以在日志中如实反映已触发的降手数保护。
    """
    try:
        if not os.path.exists(EVENT_RISK_FILE):
            return 'LOW'
        with open(EVENT_RISK_FILE, 'r', encoding='utf-8') as f:
            st = json.load(f)
        lv = str(st.get('level', 'LOW')).upper()
        if lv in ('LOW', 'MED'):
            now = time.time()
            for ev in (st.get('events') or []):
                if str(ev.get('impact', '')).lower() == 'high':
                    et = float(ev.get('time', 0) or 0)
                    if et <= now + 24 * 3600:
                        return 'ELEVATED'
        return lv
    except Exception:
        return 'LOW'


# ══ [2026-10-25 data_health] 品种级数据健康硬闸 (修复单② @risk-officer seq886 洞②) ══
# 读 risk_state.json 的 data_health 块 (write_risk_state.py 每轮读-合并独立 data_health.json, 洞①消 clobber):
#   tier=red / data_unreliable=True → 该品种新腿 0 开 (品种级硬闸, 同 D 级, 不置全市场 halt_new_entries)
#   tier=yellow                      → 该品种仓位再 ×0.5
#   读不到 / 异常                    → 从严 (整批 0 开), 同 SOP 数据旧快照; 绝不影响既有持仓管理
# 落 veto_log: gate=data_health。
DATA_HEALTH_RISKSTATE = os.path.join(DATA_DIR, 'risk_state.json')


def _veto_log_data_health(symbols, reason, lines):
    """gate=data_health 的 veto_log 落点 (修复单②)。品种级 0 开/降级留痕, 不影响既有持仓。"""
    try:
        import datetime as _dt
        vl = os.path.join(DATA_DIR, 'veto_log.jsonl')
        entry = {'ts': int(time.time()),
                 'bjt': _dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                 'gate': 'data_health',
                 'reason': reason,
                 'symbols': sorted(symbols),
                 'action': 'NEW_LEG_0_OPEN',
                 'note': '品种级数据健康硬闸 (seq886 修复单②); 不影响既有持仓管理'}
        with open(vl, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        lines.append("  [data_health] veto_log 已落 gate=data_health reason=%s 品种=%s" % (reason, sorted(symbols)))
    except Exception as _e:
        lines.append("  [data_health] veto_log 写入失败: %s" % _e)


def data_health_gate(proposals):
    """品种级数据健康闸: 返回 (red_blocked:set, yellow_symbols:set, lines:list)。

    red / data_unreliable → 该批新腿 0 开 (品种级, 同 D 级硬闸, 不置 halt_new_entries);
    yellow → 仓位 ×0.5。读不到/异常 → 从严整批 0 开 (洞③ fail-open 兜底)。
    """
    lines = []
    try:
        with open(DATA_HEALTH_RISKSTATE, 'r', encoding='utf-8') as f:
            rs = json.load(f)
        dh = rs.get('data_health')
        if not dh or 'symbols' not in dh:
            # 洞③: data_health 块缺失 (体温表未合并/文件坏) → 从严整批 0 开
            allsym = set(p.get('symbol') for p in proposals)
            lines.append("  [data_health] ⛔ data_health 块缺失 → 从严整批 0 开 (洞③ fail-open)")
            _veto_log_data_health(allsym, "missing_block", lines)
            return allsym, set(), lines
        syms = dh.get('symbols', {})
        unreliable = bool(dh.get('data_unreliable'))
        red, yellow = set(), set()
        for sym, v in syms.items():
            tier = (v or {}).get('tier')
            if tier == 'red':
                red.add(sym)
            elif tier == 'yellow':
                yellow.add(sym)
        if unreliable:
            listed = set(syms.keys())
            red = red | listed  # 洞③ 过期/不可靠: 所有列出品种一律 0 开
            lines.append("  [data_health] ⛔ data_unreliable=True(洞③) → %s 整批 0 开" % sorted(listed))
            _veto_log_data_health(listed, "data_unreliable", lines)
        else:
            if red:
                lines.append("  [data_health] ⛔ red 品种新腿 0 开(品种级硬闸): %s" % sorted(red))
                _veto_log_data_health(red, "tier_red", lines)
            if yellow:
                lines.append("  [data_health] ⚠ yellow 品种仓位 ×0.5: %s" % sorted(yellow))
        return red, yellow, lines
    except Exception as _ex:
        lines.append("  [data_health] 读闸源异常(%s) → 从严整批 0 开" % _ex)
        allsym = set(p.get('symbol') for p in proposals)
        try:
            _veto_log_data_health(allsym, "read_error:%s" % _ex, lines)
        except Exception:
            pass
        return allsym, set(), lines


# ══ [2026-10-25 daily_loss_cap] 账户级日内亏损上限硬闸 (v2.0 1.5% 钦定, @chief 终审 re-scope 取"真桥") ══
# 读 risk_state.json 的 daily_loss_cap 块 (write_risk_state.py 单源自产落盘, 无 clobber):
#   breached / data_unreliable → 本轮**全部新腿 0 开** (账户级日闸, 仅看护既有持仓, 不撤既有单)
#   读不到 / 异常            → 从严 0 开 (同 SOP 数据旧快照, 洞③ fail-open 从严)
# 落 veto_log: gate=daily_loss_cap。
DAILY_LOSS_CAP_RISKSTATE = os.path.join(DATA_DIR, 'risk_state.json')


def _veto_log_daily_loss_cap(reason, daily_loss_pct, cap_pct, lines):
    """gate=daily_loss_cap 的 veto_log 落点。账户级 0 开留痕, 不影响既有持仓管理。"""
    try:
        import datetime as _dt
        vl = os.path.join(DATA_DIR, 'veto_log.jsonl')
        entry = {'ts': int(time.time()),
                 'bjt': _dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                 'gate': 'daily_loss_cap',
                 'reason': reason,
                 'daily_loss_pct': daily_loss_pct,
                 'cap_pct': cap_pct,
                 'action': 'ACCOUNT_LEVEL_NEW_LEG_0_OPEN',
                 'note': 'v2.0 日内亏损上限 1.5% 账户级日闸(单源自产无 clobber); 既有持仓照管不撤单'}
        with open(vl, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        lines.append("  [daily_loss_cap] veto_log 已落 gate=daily_loss_cap reason=%s" % reason)
    except Exception as _e:
        lines.append("  [daily_loss_cap] veto_log 写入失败: %s" % _e)


def daily_loss_cap_gate(proposals):
    """账户级日内亏损上限闸(1.5% 钦定): 返回 (global_block:bool, lines:list)。

    breached(当日亏损>=1.5%净值) / data_unreliable(浮亏源过期/净值缺失) → 本轮全部新腿 0 开(账户级);
    读不到 / 异常 → 从严 global 0 开(同 SOP 数据旧快照)。既有持仓管理不受影响(只拦新开)。
    """
    lines = []
    try:
        with open(DAILY_LOSS_CAP_RISKSTATE, 'r', encoding='utf-8') as f:
            rs = json.load(f)
        dl = rs.get('daily_loss_cap')
        if not dl or not isinstance(dl, dict) or 'action' not in dl:
            lines.append("  [daily_loss_cap] ⛔ 字段缺失(体温表未生成/旧版) → 从严本轮全部新腿 0 开")
            _veto_log_daily_loss_cap("missing_block", None, 1.5, lines)
            return True, lines
        breached = bool(dl.get('breached'))
        unreliable = bool(dl.get('data_unreliable'))
        cap = dl.get('cap_pct', 1.5)
        dl_pct = dl.get('daily_loss_pct', 0.0)
        if breached or unreliable:
            reason = 'data_unreliable' if unreliable else 'breached'
            tag = '数据不可靠' if unreliable else '触 1.5% 上限'
            lines.append("  [daily_loss_cap] ⛔ %s(当日亏损 %.2f%% / 上限 %.1f%%) → 本轮全部新腿 0 开(账户级日闸, 既有持仓照管)" % (tag, dl_pct, cap))
            _veto_log_daily_loss_cap(reason, dl_pct, cap, lines)
            return True, lines
        return False, lines
    except Exception as _ex:
        lines.append("  [daily_loss_cap] 读闸源异常(%s) → 从严本轮全部新腿 0 开" % _ex)
        try:
            _veto_log_daily_loss_cap("read_error:%s" % _ex, None, 1.5, lines)
        except Exception:
            pass
        return True, lines


# ══ [2026-10-26 retire_freeze] RETIRE 冻结闸 (@chief 裁(a) 主动退役, L5 读方 hook 销账锚) ══
# 双源读: ①直读 retire_freeze_gate.json(producer, @risk-officer seq896 落) ②risk_state.retire_freeze
# (write_risk_state.py 每轮读-合并桥接) → 品种级新腿 0 开(scope_symbols 命中, exclude_symbols 豁免)。
# fail-closed: gate active 但字段/文件异常 → 从严 scope 全 0 开; 读不到 active → 放行(不新造冻结)。
# 落 veto_log: gate=retire_freeze。不撤既有持仓(存量 0, 只拦新开), 跟币系冻结桥同向收紧。
RETIRE_FREEZE_GATE = os.path.join(DATA_DIR, 'retire_freeze_gate.json')
RETIRE_FREEZE_RISKSTATE = os.path.join(DATA_DIR, 'risk_state.json')


def _veto_log_retire_freeze(symbols, reason, lines):
    """gate=retire_freeze 的 veto_log 落点。品种级 0 开留痕, 不影响既有持仓管理。"""
    try:
        import datetime as _dt
        vl = os.path.join(DATA_DIR, 'veto_log.jsonl')
        entry = {'ts': int(time.time()),
                 'bjt': _dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                 'gate': 'retire_freeze',
                 'reason': reason,
                 'symbols': sorted(symbols),
                 'action': 'VARIETY_LEVEL_NEW_LEG_0_OPEN',
                 'note': '@chief 裁(a) 主动退役(scope 内新腿 0 开, 不调参, OOS 30笔复验另轴解禁); 既有持仓照管不撤单'}
        with open(vl, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        lines.append("  [retire_freeze] veto_log 已落 gate=retire_freeze reason=%s" % reason)
    except Exception as _e:
        lines.append("  [retire_freeze] veto_log 写入失败: %s" % _e)


# [fail-closed 兜底 @risk-officer 13:42 洞②] 双源(gate.json + risk_state)同时读不到时的静态 scope:
#   取值 = @risk-officer seq896 落的 retire_freeze_gate.json 的 scope/exclude(与盘上闸源单一事实源一致)。
#   双源全缺 = 数据不可靠 → 从严(不新造放行), 只拦 scope 内 3 支, 不误伤 FX/金银线(不置 halt_new_entries)。
_RETIRE_FALLBACK_SCOPE = {'XAUUSD', 'BTCUSD', 'ETHUSD'}
_RETIRE_FALLBACK_EXCLUDE = {'POLUSD'}


def retire_freeze_gate(proposals):
    """品种级 RETIRE 冻结闸: 返回 (retired_blocked:set, lines:list)。

    双源读(①gate.json 直读 ②risk_state.retire_freeze 读-合并)合出 active/scope/exclude:
      active 且品种命中 scope(非 exclude) → 该品种新腿 0 开(品种级, 不撤既有单);
      [fail-closed 补严 @risk-officer 13:42 洞②] 双源全缺(两文件同时读不到) → active 置 True +
        按静态 _RETIRE_FALLBACK_SCOPE 从严 0 开(读不到快照=数据不可靠, 同 data_health 洞③ / daily_loss_cap 口径);
      单源可读 / 至少一源 active → 正常双源合并;
      两源都没 active → 放行(不新造冻结, 防误伤)。
    [锚 B 每拍 trace @risk-officer 13:42 洞①] 无论命中/静默, 每拍都往 lines(auto_cycle.log) 打
      active/src/scope/cand/hit —— 证明"每拍都读了闸", 让活循环层可销账(区分读了 vs 没读)。
    """
    lines = []
    active, scope, exclude = False, set(), set()
    gate_ok = rs_ok = False
    # 源① gate.json
    try:
        with open(RETIRE_FREEZE_GATE, 'r', encoding='utf-8') as f:
            g = json.load(f)
        gate_ok = True
        if g.get('active'):
            active = True
            scope |= set(g.get('scope_symbols') or [])
            exclude |= set(g.get('exclude_symbols') or [])
    except Exception:
        pass
    # 源② risk_state.retire_freeze (write_risk_state 每轮读-合并, 与①同向, 任一 active 即生效)
    try:
        with open(RETIRE_FREEZE_RISKSTATE, 'r', encoding='utf-8') as f:
            rf = (json.load(f) or {}).get('retire_freeze') or {}
        rs_ok = True
        if rf.get('active'):
            active = True
            scope |= set(rf.get('scope_symbols') or [])
            exclude |= set(rf.get('exclude_symbols') or [])
    except Exception:
        pass
    # [fail-closed] 双源全缺 → 数据不可靠, 按静态 scope 从严(不新造放行), 只拦 scope 内 3 支
    if not gate_ok and not rs_ok:
        active = True
        scope |= set(_RETIRE_FALLBACK_SCOPE)
        exclude |= set(_RETIRE_FALLBACK_EXCLUDE)
    if not active:
        lines.append("  [retire_freeze] trace active=0 → 放行(双源均读到且未 active, 不新造冻结)")
        return set(), lines
    blocked = scope - exclude
    cand_syms = set(p.get('symbol') for p in proposals)
    hit = blocked & cand_syms
    # [锚 B] 每拍必打 trace(成功/静默都打), 进 auto_cycle.log 供 @risk-officer 活循环层销账
    _src = []
    if gate_ok:
        _src.append('gate')
    if rs_ok:
        _src.append('risk_state')
    if not _src:
        _src.append('FALLBACK(双源全缺·从严scope=%s)' % sorted(_RETIRE_FALLBACK_SCOPE - _RETIRE_FALLBACK_EXCLUDE))
    lines.append("  [retire_freeze] trace active=1 src=%s scope=%d支 cand=%d hit=%s" % (
        '+'.join(_src), len(blocked), len(cand_syms), sorted(hit) if hit else '∅'))
    if hit:
        _veto_log_retire_freeze(hit, "scope_hit", lines)
    return blocked, lines


def retire_freeze_gate_fail_closed(proposals):
    """fail-closed 兜底入口: @chief 验收锚"挂单链实读一次 fail-closed 态"。
    [2026-10-26 补严] 真正的双源全缺 fail-closed 已内置在 retire_freeze_gate(静态 _RETIRE_FALLBACK_SCOPE
    从严 + trace src=FALLBACK), 此别名仅作显式入口保留, 调它即调主闸(行为一致)。"""
    return retire_freeze_gate(proposals)



# ══ [2026-09-24 CIO] 多智能体决策闸门 ══
# 在 audit_and_execute 前, 让 CIO(事件总监→研究→交易→风控一票否决) 过一遍。
# 返回 (blocked_set, global_block, lines):
#   global_block=True → 本轮**全部**新开仓拦截(事件HALT/日亏超限/回撤熔断)
#   blocked_set       → 仅这些 symbol 被 CIO 明确否决
#   其余 symbol       → 放行(失败开放), 下游审度司 VETO 仍会再卡一层
# CIO 未启用/异常 → 全放行, 绝不阻断现有审度司链。
_CIO_OK = None  # 缓存 CIO 是否可用, 避免每轮重复探测
_CIO_FAIL_COUNT = [0]


def _cio_gate(proposals):
    """跑 CIO 决策, 返回 (blocked_symbols:set, global_block:bool, lines:list)。

    风控一票否决(某品种日亏超限/回撤/事件)→ global_block 拦截全部新开;
    仅个别品种被 CIO 明确 D 级/负edge 否决 → 进 blocked_symbols。
    CIO 任何异常 → 全放行(失败开放), 不影响审度司链。
    """
    lines = []
    if not CIO_MODE:
        return set(), False, lines
    global _CIO_OK
    if _CIO_OK is False:
        return set(), False, lines
    try:
        import sys as _sys
        _ma_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "multi_agent")
        if _ma_dir not in _sys.path:
            _sys.path.insert(0, _ma_dir)
        import cio_orchestrator
        CIO = cio_orchestrator.CIO
        cio = CIO(DATA_DIR)
        out = cio.run_cycle()
        _CIO_OK = True
        lvl = out.get("level")
        n_ok = out.get("n_approved", 0)
        n_rej = out.get("n_rejected", 0)
        rej_syms = {r.get("symbol") for r in out.get("rejected", [])}
        global_block = False
        # ── 全局停: 事件 HALT → 本轮全不开; CIO 显式 halt_new_entries ──
        if lvl == "HALT" or out.get("halt_new_entries"):
            global_block = True
        lines.append(f"  [CIO] 多智能体决策: 放行{n_ok}/拒{n_rej} (事件级={lvl})"
                     + ("  ⛔全局停" if global_block else ""))
        return rej_syms, global_block, lines
    except Exception as e:
        _CIO_OK = False
        _CIO_FAIL_COUNT[0] += 1
        lines.append(f"  [CIO] 闸门异常(放行全部, 不阻断审度司): {type(e).__name__} {e}")
        return set(), False, lines


def main():
    sys.excepthook = _crash_hook
    args = sys.argv[1:]
    # 异步进化子进程入口: 只跑 Walk-Forward 写 state 后退出(不进 live 循环)
    if '--evolve-only' in args:
        rounds = EVOLVE_ROUNDS
        budget = ASYNC_EVOLVE_BUDGET_SEC_PER_SYM
        for a in args:
            if a.startswith('--rounds='):
                try:
                    rounds = max(5, int(a.split('=')[1]))
                except Exception:
                    pass
            elif a.startswith('--budget='):
                try:
                    budget = max(30, int(a.split('=')[1]))
                except Exception:
                    pass
        print(f"[{time.strftime('%H:%M:%S')}] [进化子进程] 启动 Walk-Forward 自进化 "
              f"({rounds}轮, 单品种预算{budget}s, 真实 MT5 回测, 只读不下单)...")
        try:
            ce.run_continuous_evolution(max_rounds=rounds, per_symbol_budget_sec=budget)
            print(f"[{time.strftime('%H:%M:%S')}] [进化子进程] 完成, 已写 evolution_state.json")
        except Exception as e:
            print(f"[进化子进程] 失败: {e}")
        sys.exit(0)
    if '--selftest' in args:
        import test_supervisor
        import test_scanner
        ok1 = test_supervisor.run()
        ok2 = test_scanner.run()
        # 独立增强测试: RF 双方向择优翻转 + 点差摩擦护栏 (吸收 Supreme_EA 坑#3/#4)
        # 未接入 run() 主组, 此处显式纳入 CI, 避免回归漏检.
        ok3 = test_scanner.test_rf_direction_flip()
        ok4 = test_scanner.test_spread_guard()
        print(f"[selftest] supervisor={ok1} scanner={ok2} "
              f"rf_flip={ok3} spread_guard={ok4}")
        sys.exit(0 if (ok1 and ok2 and ok3 and ok4) else 1)

    live = '--live' in args
    if live and not _live_lock_acquire():
        sys.exit(0)
    _beat()  # 启动即心跳, 让 watchdog 立即可见 live 存活
    loop = '--loop' in args
    interval = 120
    for a in args:
        if a.startswith('--interval='):
            try:
                interval = max(10, int(a.split('=')[1]))
            except Exception:
                pass

    built = _build(live)
    if built is None:
        print("[交易员] MT5 连接失败, 退出。")
        sys.exit(1)
    guardian, hunter, supervisor = built

    if loop:
        print(f"[交易员] 进入自主交易循环, 每 {interval}s 一轮 "
              f"(live={live}); Ctrl+C 退出")
        # 软重置: 每 2 小时重建三联体, 防 MT5 连接/状态长期泄漏
        #   继承式进化后提速1倍(原4h), 且异步不阻塞交易, 进化频率=账户复利频率
        soft_reset_sec = 1 * 3600   # 最高进化速度: 每 1h 异步触发一次(不阻塞交易)
        start = time.time()
        # 漂移监控: 启动即跑一次(验证只读监控无报错), 后续在软重置后节流(每6次/24h)
        drift_counter = 0
        last_drift_ts = start
        _run_drift_once()
        # 启动即触发一次有界自进化(消除"干等4h"痛点, 真正"时刻保持进化状态"):
        #   只读回测不下单 → 与后续 live 交易无并发冲突; 完成后热加载新最优参数.
        try:
            print(f"[{time.strftime('%H:%M:%S')}] 启动自进化: 各品种快速重优化 "
                  f"({STARTUP_EVOLVE_ROUNDS}轮/品种, 真实 MT5 回测, 只读不下单)...")
            ce.run_continuous_evolution(
                max_rounds=STARTUP_EVOLVE_ROUNDS,
                per_symbol_budget_sec=STARTUP_EVOLVE_MAX_SEC_PER_SYM)
            # 热加载新最优参数到猎场司(不重建 MT5 连接, 避免中断看护)
            hunter.strategies = ps.load_all_best_strategies()
            print(f"[{time.strftime('%H:%M:%S')}] 启动自进化完成, 新最优策略已热加载(本轮即生效)")
        except Exception as e:
            print(f"[启动自进化] 失败(沿用旧最优策略, 不影响交易): {e}")
        # 进化热加载基准: 记录当前 state mtime, 子进程写新 state 后自动热加载
        _evo_mtime = [_state_mtime()]
        try:
            while True:
                try:
                    _beat()  # 每轮心跳, 供 watchdog 判断存活
                    if not guardian.healthy():
                        print(f"[{time.strftime('%H:%M:%S')}] MT5 异常, 重建中...")
                        _nb = _build(live)
                        if _nb is not None:
                            guardian, hunter, supervisor = _nb
                        else:
                            # [2026-08-27 修复] 重建失败(如真仓防护server空)时
                            # 不要每2分钟死循环重试: 退避等待 + 强制重连MT5再试.
                            print(f"[{time.strftime('%H:%M:%S')}] 重建失败, "
                                  f"60s后重试 (MT5重连中)...")
                            try:
                                import MetaTrader5 as _m5
                                _m5.shutdown()
                            except Exception:
                                pass
                            time.sleep(60)
                            continue
                    # 进化热加载(异步子进程写完即生效, 不阻塞主循环)
                    _evo_mtime[0] = _maybe_hotload_evolved(hunter, _evo_mtime)
                    if time.time() - start > soft_reset_sec:
                        print(f"[{time.strftime('%H:%M:%S')}] 周期软重置: 异步自进化重优化 + 重建三联体")
                        # 进化异步化: 拉独立子进程跑(自己连MT5只读回测), 主循环不阻塞;
                        # 新 state 由 _maybe_hotload_evolved 自动热加载.
                        _launch_async_evolution()
                        built = _build(live) or (guardian, hunter, supervisor)
                        guardian, hunter, supervisor = built
                        start = time.time()
                        # 漂移监控节流: 每 6 次软重置 或 距上次 >24h 跑一次(只读, 不交易)
                        drift_counter += 1
                        if drift_counter >= 6 or (time.time() - last_drift_ts) > 24 * 3600:
                            _run_drift_once()
                            drift_counter = 0
                            last_drift_ts = time.time()
                    try:
                        print("─" * 60)
                    except Exception:
                        print("-" * 60)
                    print(time.strftime('%Y-%m-%d %H:%M:%S'), "交易轮次:")
                    print(_cycle(guardian, hunter, supervisor, live))
                except Exception:
                    print(f"[{time.strftime('%H:%M:%S')}] [交易员] 本轮异常"
                          f"(已跳过, 详见traceback):")
                    traceback.print_exc()
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\n[交易员] 自主交易循环已停止。")
        return

    print(_cycle(guardian, hunter, supervisor, live))
    print("\n[JSON]")
    print(json.dumps({}, indent=2))


if __name__ == '__main__':
    main()
