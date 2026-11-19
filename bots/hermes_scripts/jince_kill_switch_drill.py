# -*- coding: utf-8 -*-
r"""kill switch 月度纸面演练包装 (cron script 字段不接受参数, 薄包装调 watch --drill)。"""
import runpy
import sys

sys.argv = ["jince_kill_switch_watch.py", "--drill"]
runpy.run_path(r"E:\workbuddy\国外模型\hermes\scripts\jince_kill_switch_watch.py", run_name="__main__")
