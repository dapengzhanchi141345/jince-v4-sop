"""
金策宗师团 v5.0 — BTCUSD 自动交易启动器
直接双击运行，或从命令行执行
"""
import sys, os

# 修复编码问题
sys.stdin.reconfigure(encoding='utf-8', errors='replace')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

LOG_FILE = "E:/GoldstrategyEngine/logs/daemon.log"

def log(msg):
    t = __import__('datetime').datetime.now().strftime('%H:%M:%S')
    safe = msg.replace('\u2705','[OK]').replace('\u274c','[X]').replace('\u26a0\ufe0f','[!]')
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f'[{t}] {msg}\n')
    except:
        pass  # 文件写失败不阻塞
    try:
        print(f'[{t}] {safe}')
    except:
        try:
            print(f'[{t}] {msg.encode("ascii", errors="replace").decode("ascii")}')
        except:
            pass

log('='*50)
log('Goldstrategy Guild v5.0 BTCUSD Auto Trader — Starting...')
log('='*50)

# ───────── 检查MT5终端 ─────────
MT5_PATH = r"C:\Program Files\TMGM MT5 Terminal\terminal64.exe"
if not os.path.exists(MT5_PATH):
    log(f'[!] MT5 not found at: {MT5_PATH}')
    log('[!] Please install MT5 or check the path')
    input('\nPress Enter to exit...')
    sys.exit(1)

# ───────── 启动AutoDaemon ─────────
log('[OK] MT5 found, launching auto_trader...')

# 导入并运行主引擎
sys.path.insert(0, 'E:/GoldstrategyEngine')
from auto_daemon import run_daemon

if __name__ == '__main__':
    run_daemon()
