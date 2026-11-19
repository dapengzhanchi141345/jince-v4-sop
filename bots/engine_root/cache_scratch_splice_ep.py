# -*- coding: utf-8 -*-
"""[L5 2026-11-04] crypto_pending.py 攒样状态无关 splice: 例外腿块 -> _run_obs_exception_legs() 双态调用."""
import io

p = "multi_agent/trading/crypto_pending.py"
lines = open(p, encoding="utf-8").read().split("\n")  # 0-indexed; L(n) = lines[n-1]

# --- 断言锚点 (1-indexed 行号, 拼前逐条验) ---
assert lines[1159-1].strip() == "try:", lines[1159-1]
assert lines[1160-1].strip() == "_excs = _freeze_exceptions()", lines[1160-1]
assert "维持全冻" in lines[1220-1], lines[1220-1]
assert lines[1219-1].strip().startswith("except Exception as _exe:"), lines[1219-1]
assert "def _reconcile_orphans" in lines[1041-1], lines[1041-1]
assert lines[1390-1].strip() == "for plan in tier2:", lines[1390-1]
assert "_try_place(plan," in lines[1391-1] and "腿2" in lines[1391-1], lines[1391-1]

# --- 1) 取冻结分支块 L1159-1220, 去 4 空格缩进变函数体 (原块基缩进 8sp, 函数体需 4sp) ---
block = lines[1159-1:1220]
ded = []
for ln in block:
    assert ln.startswith("    ") and not ln.startswith("        ") or ln.startswith("        ") or ln.strip() == "", repr(ln[:40])
    ded.append(ln[4:] if ln.strip() else ln)
fn_body = "\n".join(ded)
fn_body = fn_body.replace("n_new += 1", "n_placed += 1")
fn_body = fn_body.replace("n_blocked += 1", "n_failed += 1")
fn_body = fn_body.replace('[例外腿] L4 冻结白名单放行', '[例外腿{label}] L4 冻结白名单放行')
fn_body = fn_body.replace('[例外腿] {_exsym} 已有活腿/持仓', '[例外腿{label}] {_exsym} 已有活腿/持仓')
fn_body = fn_body.replace("不影响全冻循环", "不影响主循环{label}")
fn_body = fn_body.replace("维持全冻): ", "维持全冻{label}): ")

FN_HEAD = (
    "def _run_obs_exception_legs(st, log, equity, research, dry_run, label=\"\"):\n"
    "    \"\"\"[L5 2026-11-04 攒样状态无关] L4 白名单例外腿 (POLUSD 等, one_leg_repost, 0.5x 封顶)\n"
    "    OOS 攒样带腿生成 + 挂单, 冻结/非冻结两态都由 run_cycle 调用.\n"
    "    根因修复: 11-04 06:24 冻结闸 until_ts 自然过期 -> _crypto_frozen()=False ->\n"
    "    原代码块只活在冻结分支里 -> 静默消失 -> OOS 攒样 0 笔/天, \"带腿首拍实挂\"不成立.\n"
    "    带腿 = 既有观察腿 (0.5x 封顶 + kill-switch 30 笔, L4 三层维持裁定), 非新腿,\n"
    "    与冻结闸生命周期解耦; 白名单仍认 crypto_freeze_gate.json 的 active 标志 (L4 撤闸才消失).\n"
    "    失败开放: 白名单读异常/单品种异常 -> 留痕不崩链. 返回 (n_placed, n_failed).\"\"\"\n"
    "    import MetaTrader5 as mt5\n"
    "    n_placed, n_failed = 0, 0\n"
)
FN_TAIL = "\n    return n_placed, n_failed\n\n"
FUNC = (FN_HEAD + fn_body + FN_TAIL).split("\n")

# --- 2) 冻结分支: 块 -> 函数调用 (外层 try/except fail-open 形状不变) ---
frozen_repl = """        # [L5 2026-11-04 攒样状态无关] 例外腿 (POLUSD 带腿 0.5x) 抽成 _run_obs_exception_legs,
        # 冻结/非冻结两态都调 (06:24 冻结闸 until_ts 自然过期后, 原块只活在冻结分支 -> 消失).
        try:
            _np_exc, _nf_exc = _run_obs_exception_legs(st, log, equity, research, dry_run)
            n_new += _np_exc
        except Exception:
            pass""".split("\n")

# --- 3) 非冻结分支: tier2 挂单后插入同函数调用 ---
nf_repl = """        # [L5 2026-11-04 攒样状态无关] 非冻结态也生成白名单带腿 (POLUSD OOS 攒样 0.5x,
        # L4 三层维持裁定; 常规腿仍由 exp_r 总闸全拒 -> 币系 0 新腿纪律不变).
        try:
            _np_exc, _nf_exc = _run_obs_exception_legs(st, log, equity, research, dry_run, label="·非冻结")
            n_new += _np_exc
            n_blocked += _nf_exc
        except Exception:
            pass""".split("\n")

# 自底向上拼 (行号不漂移)
new = lines[:]
new[1391:1391] = nf_repl
new[1158:1220] = frozen_repl
new[1040:1040] = FUNC

open(p, "w", encoding="utf-8", newline="").write("\n".join(new))
print("splice done: %d -> %d lines" % (len(lines), len(new)))
