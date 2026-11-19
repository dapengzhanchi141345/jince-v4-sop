# -*- coding: utf-8 -*-
"""根治 11:31 全链被掐(0xC000013A)复发源: JinCe* 交易任务电池开关.
StopIfGoingOnBatteries=True + DisallowStartIfOnBatteries=True = 一回电池全链被掐死 ->
白天拉根/合盖/睡眠 就漏一整轮 30min 全链(chief 心跳停, 点位单不进管道). 全部关掉让交易链跑电池.
只动 JinCe* 交易链任务, 不碰 HermesDesktop/Gateway 等系统任务."""
import subprocess, json

def ps(script, timeout=90):
    r = subprocess.run(["powershell", "-NoProfile", "-Command", "chcp 65000 | Out-Null; " + script],
                       capture_output=True, text=True, timeout=timeout, creationflags=0x08000000)
    return (r.stdout or "").strip(), r.returncode

# 1. 列 JinCe* 任务的电池开关
out, rc = ps("Get-ScheduledTask -TaskName 'JinCe*' | "
             "Select-Object TaskName,@{n='StopIfBat';e={$_.Settings.StopIfGoingOnBatteries}},"
             "@{n='DisallowBat';e={$_.Settings.DisallowStartIfOnBatteries}} | "
             "ConvertTo-Json")
print("=== JinCe* 任务电池开关(修复前) ===")
try:
    for t in json.loads(out):
        print("  ", t["TaskName"], "| StopIfGoingOnBatteries:", t.get("StopIfBat"),
              "| DisallowStartIfOnBatteries:", t.get("DisallowBat"))
except Exception as e:
    print("  解析失败:", str(e)[:80], out[:200])

# 2. 全关掉(跑电池)
print("\n=== 关闭电池停跑开关 ===")
out2, rc2 = ps("Get-ScheduledTask -TaskName 'JinCe*' | ForEach-Object { "
               "$t=$_; Set-ScheduledTask -TaskName $t.TaskName -Settings "
               "(New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries) | Out-Null; "
               "Write-Output ('set '+$t.TaskName) } | Out-String")
print(out2.strip() or "(无匹配)")

# 3. 复验
print("\n=== 复验(修复后) ===")
out3, _ = ps("Get-ScheduledTask -TaskName 'JinCe*' | "
             "Select-Object TaskName,@{n='StopIfBat';e={$_.Settings.StopIfGoingOnBatteries}},"
             "@{n='DisallowBat';e={$_.Settings.DisallowStartIfOnBatteries}} | ConvertTo-Json")
try:
    for t in json.loads(out3):
        print("  ", t["TaskName"], "| StopIfBat:", t.get("StopIfBat"),
              "| DisallowBat:", t.get("DisallowBat"),
              "| 下一轮:", end=" ")
    nxt, _ = ps("Get-ScheduledTaskInfo -TaskName JinCeAutoCycle | Select-Object -ExpandProperty NextRunTime")
    print(nxt.strip())
except Exception as e:
    print("  复验失败:", str(e)[:80], out3[:200])
