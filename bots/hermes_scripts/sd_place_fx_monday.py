"""金策模拟户周一 21:05 全品种挂单 (no_agent cron): 30 品种 ~60 单
步骤: ① 刷新 30 品种 M15 数据 (失败=硬退出, 防"数据没刷+区闸拦=0挂单"最坏组合)
      ② 重置同日区闸 state (周一一次触发非重跑, 安全; 防上日 state 的 zone_dk 拦整批)
      ③ 挂单 (分品种参数表 sd_symbol_params.json 自动生效)
      ④ 挂=0 或 败>0 显式告警行 (cron 可见)
stdout = 挂单结果摘要 (报给李彦明, 北京时间口径)."""
import subprocess, sys, os, json, time

ATE = r"D:\workbuddy\binaries\python\versions\3.13.12\python.exe"
# M修复: TMP/TEMP/TMPDIR 重定向 E 盘 (子进程 pycache 不落 C 盘)
ENV = {k: v for k, v in os.environ.items() if k not in ("PYTHONHOME", "PYTHONPATH",
                                                        "TMP", "TEMP", "TMPDIR")}
ENV.update({"TMP": r"E:\GoldstrategyEngine\scratch", "TEMP": r"E:\GoldstrategyEngine\scratch",
            "TMPDIR": r"E:\GoldstrategyEngine\scratch"})
os.makedirs(ENV["TMP"], exist_ok=True)

# ① 刷新数据 (硬失败: 数据没刷 -> 区不前进 -> 挂不上/挂旧区, 必须停)
f = subprocess.run([ATE, "-u", r"E:\GoldstrategyEngine\research\allsyms_fetch_20261115.py"],
                   capture_output=True, timeout=1200, env=ENV)
fout = f.stdout.decode("utf-8", "replace")
tail = fout.strip().splitlines()[-1] if fout.strip() else "(无输出)"
print("数据刷新: exit=%d %s" % (f.returncode, tail))
if f.returncode != 0:
    print("[ALARM] 数据刷新失败 -> 挂单中止(防旧区/零挂单静默), 请检查 MT5 终端", fout[-500:])
    sys.exit(1)

# ② 重置同日区闸 state (周一 21:05 一次性任务, 非重跑; 防上日 state zone_dk 拦整批)
_st = r"E:\GoldstrategyEngine\data\sd_all_zone_state.json"
if os.path.exists(_st):
    try:
        _old = json.load(open(_st, encoding="utf-8"))
        os.remove(_st)
        print("区闸 state 已重置 (原 last_zone_dk=%s, 周一新批放行)" % _old.get("last_zone_dk"))
    except Exception as e:
        print("区闸 state 重置失败(不阻塞): %s" % e)

# ③ 全品种挂单 (30 品种, 分品种参数表自动读)
cmd = [ATE, "-u", r"E:\GoldstrategyEngine\research\place_sd_all_20261115.py",
       "--params", r"E:\GoldstrategyEngine\research\sd_all_best_params.json", "--live"]
r = subprocess.run(cmd, capture_output=True, timeout=900, env=ENV)
out = r.stdout.decode("utf-8", "replace")
keep = [l for l in out.splitlines() if not l.startswith("[RETRY")]
print("周一全品种挂单(北京%s):" % time.strftime("%H:%M"), "\n".join(keep[-70:]))
if r.returncode != 0:
    print("STDERR:", r.stderr.decode("utf-8", "replace")[-800:])
    sys.exit(1)

# ④ L4: 挂=0 或 败>0 显式告警
sum_line = next((l for l in out.splitlines() if l.startswith("=== 汇总")), "")
if sum_line and ("挂=0" in sum_line or "败=0" not in sum_line):
    print("[ALARM] 挂单异常: %s (FX 10015 禁挂单/股指 22:30 才开 属预期, 请核对败单清单; "
          "败单品种 24h 内可手动重挂)" % sum_line)
if "同日区闸" in out:
    print("[ALARM] 被同日区闸整批拦截(数据刷新后 dk 仍未前进?) -> 需人工清 state 重跑")
