# -*- coding: utf-8 -*-
"""
安全启动器：绕过 deep_learning_optimizer(torch) 运行 technical_analyzer.py
背景：venv 内 `import torch` 直接段错误(EXIT 139)，且段错误无法被 try/except 捕获，
      导致 technical_analyzer.py 在可选 DL 模块导入处整体崩溃。
做法：预先向 sys.modules 注入一个不含 DLOptimizer 的桩模块，
      使 `from deep_learning_optimizer import DLOptimizer` 抛出可捕获的 ImportError，
      分析器自动降级为 HAS_DL=False（纯规则模式）继续运行。
用法：python run_analyzer_nodl.py
"""
import sys, types, runpy

_stub = types.ModuleType("deep_learning_optimizer")
_stub.__doc__ = "stub: torch import segfaults, DL disabled"
sys.modules["deep_learning_optimizer"] = _stub

print("  [启动器] 已禁用深度学习模块 (torch 段错误)，以纯规则模式运行。")
runpy.run_path(r"E:\GoldstrategyEngine\technical_analyzer.py", run_name="__main__")
