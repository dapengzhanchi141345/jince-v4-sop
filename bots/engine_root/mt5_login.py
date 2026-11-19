# -*- coding: utf-8 -*-
"""mt5_login.py — 统一登录模块, 铁律"交易密码 0 落盘"的落点。
优先级: ① 终端已登录态(mt5.account_info 有值即用) ② gitignore 的 .env(MT5_PASS) ③ 报错拒跑。
各脚本改法: 删掉 `mt5.login(号, password="Lym...", server=...)` 一行, 换成
    import mt5_login
    ok, why = mt5_login.ensure_login(60137964)
    if not ok: raise SystemExit(why)
"""
import os

# .env 路径 = 引擎根, gitignore 里已有 (见 .gitignore: .env / *.env)
_ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")

def _read_env_pass():
    if os.path.exists(_ENV_PATH):
        for line in open(_ENV_PATH, encoding="utf-8"):
            if line.startswith("MT5_PASS="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None

def ensure_login(account_id, server=None):
    """返回 (ok, 说明)。0 硬编码密码。
    前置: 调用方必须先 mt5.initialize(), 否则"已登录态"分支 account_info() 返回 None 误判成无登录态。"""
    import MetaTrader5 as mt5
    # 1) 终端已登录态 (最常见: 终端常驻登录)
    info = mt5.account_info()
    if info is not None and (server is None or getattr(info, "server", None) == server):
        return True, "终端已登录态直接用 (0 密码)"
    # 2) 初始化 + .env
    if not mt5.initialize():
        return False, "mt5.initialize 失败 (终端没起)"
    pw = _read_env_pass()
    if pw is None:
        mt5.shutdown()
        return False, "无终端登录态且 .env 无 MT5_PASS (铁律: 密码 0 落盘, 请配 .env 或先登录终端)"
    ok = mt5.login(account_id, password=pw, server=server) if server else mt5.login(account_id, password=pw)
    return (ok, "login 成功 (.env)") if ok else (False, "login 失败 (.env 密码错或号不对)")

if __name__ == "__main__":
    ok, why = ensure_login(60137964)
    print("smoke:", ok, why)
