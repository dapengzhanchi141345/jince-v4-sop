import psutil, os, sys
me = psutil.Process().pid
procs = [p.info for p in psutil.process_iter(attrs=['pid', 'cmdline', 'ppid']) if p.info['pid'] != me]
rt = [(p['pid'], p['ppid']) for p in procs
      if any('run_trader.py' in c for c in (p['cmdline'] or [])) and '-c' not in ' '.join(p['cmdline'] or [])]
wd = [(p['pid'], p['ppid']) for p in procs if any('watchdog.py' in c for c in (p['cmdline'] or []))]
print('run_trader:', rt)
print('watchdog:', wd)
pid = 'E:/GoldstrategyEngine/data/live.pid'
print('live.pid:', open(pid).read().strip() if os.path.exists(pid) else 'MISSING')
