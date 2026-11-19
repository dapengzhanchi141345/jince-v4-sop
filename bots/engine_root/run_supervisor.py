# run_supervisor.py — 监军司运行器
#
# 用法:
#   python run_supervisor.py                  # 默认 DRY-RUN: 只报告决策, 不执行
#   python run_supervisor.py --live          # 真执行: 经审度司审计后平/改SL
#   python run_supervisor.py --live --loop   # 实时循环监督 (每 --interval 秒一轮)
#   python run_supervisor.py --selftest      # 离线单测决策引擎 (不连 MT5)
#
# 安全默认: dry_run=True, auto_confirm=False。真执行需 --live, 且仍受
#   审度司 VETO + LIVE_TRADING_ENABLED 硬开关双重约束。
# 循环模式 (--loop) 用于"时刻盯盘": 单进程内每 interval 秒扫一轮,
#   每轮异常被捕获不影响下一轮, 仅看护既有持仓、绝不新开仓。

import sys
import time
import json
import os
import traceback
import guardian_executor as ge
import position_supervisor as ps


def _crash_hook(exc_type, exc_value, exc_tb):
    """崩溃钩子: 任何未捕获异常落盘, 不静默丢失 (吸收对方守护进程
    sys.excepthook 崩溃落盘的设计)。"""
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        log = os.path.join(here, 'logs', 'supervisor_crash.log')
        os.makedirs(os.path.dirname(log), exist_ok=True)
        with open(log, 'a', encoding='utf-8') as f:
            f.write(time.strftime('%Y-%m-%d %H:%M:%S') + " CRASH\n")
            f.write(''.join(traceback.format_exception(exc_type, exc_value, exc_tb)))
            f.write("\n")
    except Exception:
        pass
    sys.__excepthook__(exc_type, exc_value, exc_tb)


def _reconnect(sup, live):
    """MT5 断线重连: 重建监军司并重新连接 (吸收对方守护进程重连韧性)。"""
    try:
        sup = ps.PositionSupervisor(auto_confirm=live, dry_run=not live)
        if live:
            ge.LIVE_TRADING_ENABLED = True
        if sup.connect():
            print(f"[{time.strftime('%H:%M:%S')}] MT5 重连成功")
            return sup
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] 重连异常: {e}")
    return None


def main():
    sys.excepthook = _crash_hook
    args = sys.argv[1:]
    if '--selftest' in args:
        import test_supervisor
        ok = test_supervisor.run()
        sys.exit(0 if ok else 1)

    live = '--live' in args
    loop = '--loop' in args
    interval = 120
    for a in args:
        if a.startswith('--interval='):
            try:
                interval = max(10, int(a.split('=')[1]))
            except Exception:
                pass

    sup = ps.PositionSupervisor(auto_confirm=live, dry_run=not live)
    if live:
        # 真实下单总闸 (用户已授权模拟实盘)
        ge.LIVE_TRADING_ENABLED = True
    if not sup.connect():
        print("[监军司] MT5 连接失败, 退出。")
        sys.exit(1)

    if loop:
        print(f"[监军司] 进入循环监督模式, 每 {interval}s 一轮 "
              f"(live={live}); Ctrl+C 退出")
        # 软重置: 每 4 小时重建监军司, 防 MT5 连接/状态长期泄漏
        soft_reset_sec = 4 * 3600
        start = time.time()
        try:
            while True:
                try:
                    if not sup.healthy():
                        print(f"[{time.strftime('%H:%M:%S')}] MT5 连接异常, 重连中...")
                        sup = _reconnect(sup, live)
                        if sup is None:
                            time.sleep(interval)
                            continue
                    if time.time() - start > soft_reset_sec:
                        print(f"[{time.strftime('%H:%M:%S')}] 周期软重置 (重建监军司)")
                        sup = _reconnect(sup, live) or sup
                        start = time.time()
                    results = sup.supervise_once()
                    print("─" * 50)
                    print(time.strftime('%Y-%m-%d %H:%M:%S'), "监督轮次:")
                    print(sup.report(results))
                except Exception as e:
                    print(f"[监军司] 本轮异常(已跳过): {e}")
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\n[监军司] 循环监督已停止。")
        return

    results = sup.supervise_once()
    print(sup.report(results))
    print("\n[JSON]")
    print(json.dumps(results, indent=2, ensure_ascii=False, default=str))


if __name__ == '__main__':
    main()
