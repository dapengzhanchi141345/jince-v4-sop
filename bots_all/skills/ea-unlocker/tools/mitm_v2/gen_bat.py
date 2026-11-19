#!/usr/bin/env python
"""生成一键落地 bat (MT5 代理路线 + 还原)
路线 B: 不改系统 DNS, 在 MT5 的 WebRequest 里设代理 127.0.0.1:8888 + 信任本地 CA。
本脚本生成:
  setup_b_route.bat  — 检查端口占用、提示手动在 MT5 设置代理(不能代替 MT5 界面)
  revert_b_route.bat — 清理用户级 CA 信任
路线 A (hosts+根CA+本地443, 管理员) 生成:
  setup_a_route.bat  — 需管理员; 写 hosts、装根 CA、起 local443_v2
  revert_a_route.bat — 删 hosts 行、删根 CA
"""
import os, sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import config

def gbk_lines(text):
    return text

def main():
    out = os.path.join(BASE, "batch")
    os.makedirs(out, exist_ok=True)
    ca_crt = os.path.join(BASE, "ca", "ca.crt")
    # ---- B 路线 ----
    with open(os.path.join(out, "setup_b_route.bat"), "w", encoding="gbk") as f:
        f.write('@echo off\r\nrem ===== B路线: MT5代理劫持(不改系统DNS) =====\r\n'
                'rem 前置: 1)运行过 gen_ca.py  2)双击过 ca/import_ca.bat (用户级信任CA)\r\n'
                'echo 检查本地代理端口 8888 占用情况:\r\n'
                'netstat -ano | findstr "127.0.0.1:8888"\r\n'
                'echo.\r\n'
                'echo 启动 MITM 代理: python "%s\\run_mitm_v2.py"\r\n'
                'start "" python "%s\\run_mitm_v2.py"\r\n'
                'echo.\r\n'
                'echo ==== 手动操作(我无法代你在 MT5 界面里点) ====\r\n'
                'echo 1. MT5 顶部工具栏: 工具 - 选项 - 导航\r\n'
                'echo 2. 勾选 "使用 HTTP 代理", 类型 HTTP, 地址 127.0.0.1 端口 8888\r\n'
                'echo 3. 在 "允许 WebRequest" 里加入厂商域名(如 %s)\r\n'
                'echo 4. 重启 MT5, 挂 EA, 看是否过验证\r\n'
                'pause\r\n' % (BASE, BASE, config.default_sni))
    with open(os.path.join(out, "revert_b_route.bat"), "w", encoding="gbk") as f:
        f.write('@echo off\r\nrem ===== B路线还原: 撤用户级 CA 信任 + 提示关代理 =====\r\n'
                'certutil -delstore -user -f "EA Unlocker Local CA"\r\n'
                'echo 别忘了: 关掉 python run_mitm_v2 进程 + 清掉 MT5 代理设置(工具-选项-导航 取消代理)\r\n'
                'pause\r\n')
    # ---- A 路线(管理员, hosts+根CA+本地443) ----
    with open(os.path.join(out, "setup_a_route_admin.bat"), "w", encoding="gbk") as f:
        f.write('@echo off\r\nrem ===== A路线: hosts+系统根CA+本地443 (需管理员运行) =====\r\n'
                'rem 还原: 双击 revert_a_route_admin.bat\r\n'
                'echo 检查 443/80 占用:\r\n'
                'netstat -ano | findstr ":443 :80"\r\n'
                'echo 若被占(如旧 local443 / 其它服务), 需先处理, 别擅自杀!\r\n'
                'pause\r\n'
                'echo 写 hosts (需要管理员; 会写入 127.0.0.1 %s):\r\n'
                'echo 127.0.0.1 %s >> C:\\Windows\\System32\\drivers\\etc\\hosts\r\n'
                'echo 装系统根 CA (需要管理员):\r\n'
                'certutil -addstore "Root" "%s"\r\n'
                'echo 启动本地 443/80 服务:\r\n'
                'start "" python "%s\\local443_v2.py"\r\n'
                'echo 完成。重启 MT5 再挂 EA 测试。\r\n'
                'pause\r\n' % (config.default_sni, config.default_sni, ca_crt, BASE))
    # 还原 A 路线: 删 hosts 行 + 撤根 CA (用变量避免转义地狱)
    sni_pat = config.default_sni
    ps_line = ('powershell -Command "(gc $env:TEMP\\hosts.bak.eaulk) '
               '| where {$_ -notmatch "%s"} | set-content $env:TEMP\\hosts.bak.eaulk"' % sni_pat)
    with open(os.path.join(out, "revert_a_route_admin.bat"), "w", encoding="gbk") as f:
        f.write('@echo off\r\nrem ===== A路线一键还原 (需管理员) =====\r\n'
                'rem 1) 备份并删 hosts 行\r\n'
                'copy /Y C:\\Windows\\System32\\drivers\\etc\\hosts "%TEMP%\\hosts.bak.eaulk"\r\n'
                + ps_line + '\r\n'
                'copy /Y "%TEMP%\\hosts.bak.eaulk" C:\\Windows\\System32\\drivers\\etc\\hosts\r\n'
                'rem 2) 撤系统根 CA\r\n'
                'certutil -delstore "Root" "EA Unlocker Local CA"\r\n'
                'rem 3) 提示: 手动关掉 local443_v2 进程\r\n'
                'echo 还原完成, 记得关掉 python local443_v2 进程\r\n'
                'pause\r\n')
    print("已生成到:", out)
    for f_ in sorted(os.listdir(out)):
        print("  " + f_)

if __name__ == "__main__":
    main()
