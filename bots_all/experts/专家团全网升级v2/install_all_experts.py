# -*- coding: utf-8 -*-
"""把 my-experts 市场中的 37 位专家全部“安装”到专家中心。

原理：专家中心只显示 plugins/installed_plugins.json 中注册过的插件。
市场里有 37 个，但之前只安装过 7 个，所以只显示 7 个。
本脚本：复制市场源 -> cache/my-experts/<name>/<version>/，并写入注册表。
旧版本缓存目录会先备份到 E 盘，不做删除。
"""
import json, os, io, shutil, datetime

MARKET_ROOT = r"C:\Users\ASUS\.workbuddy\plugins\marketplaces\my-experts"
PLUGINS_DIR = os.path.join(MARKET_ROOT, "plugins")
CACHE_DIR = r"C:\Users\ASUS\.workbuddy\plugins\cache\my-experts"
REG_FILE = r"C:\Users\ASUS\.workbuddy\plugins\installed_plugins.json"
MARKET_ID = "my-experts"

BACKUP_ROOT = r"E:\workbuddy\专家团\专家团全网升级v2\安装备份_20260909"
os.makedirs(BACKUP_ROOT, exist_ok=True)

ts = datetime.datetime.now().isoformat(timespec="seconds")

# 1. 备份注册表
shutil.copy2(REG_FILE, os.path.join(BACKUP_ROOT, "installed_plugins.json.bak"))
print("已备份 installed_plugins.json ->", BACKUP_ROOT)

idx = json.load(io.open(os.path.join(MARKET_ROOT, ".codebuddy-plugin", "marketplace.json"), encoding="utf-8"))
names = [p["name"] for p in idx["plugins"]]

reg = json.load(io.open(REG_FILE, encoding="utf-8"))
reg.setdefault("plugins", {})

ok, fail = [], []
for name in sorted(names):
    src = os.path.join(PLUGINS_DIR, name)
    pj = os.path.join(src, ".codebuddy-plugin", "plugin.json")
    if not os.path.exists(pj):
        fail.append((name, "无 plugin.json"))
        continue
    ver = json.load(io.open(pj, encoding="utf-8")).get("version", "1.0.0")

    # 2. 旧缓存目录先备份移走，避免多版本重复显示
    old_dir = os.path.join(CACHE_DIR, name)
    if os.path.isdir(old_dir):
        bak = os.path.join(BACKUP_ROOT, "cache_old", name)
        os.makedirs(os.path.dirname(bak), exist_ok=True)
        if os.path.exists(bak):
            shutil.rmtree(bak)
        try:
            shutil.move(old_dir, bak)
        except Exception as e:
            print("  ! 旧缓存移动失败 %s: %s" % (name, e))

    # 3. 复制最新版本到 cache
    dst = os.path.join(CACHE_DIR, name, ver)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copytree(src, dst, dirs_exist_ok=True)

    # 4. 写注册表
    key = "%s@%s" % (name, MARKET_ID)
    now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")
    old = reg["plugins"].get(key, [{}])
    installed_at = old[0].get("installedAt", now) if old else now
    reg["plugins"][key] = [{
        "scope": "user",
        "installPath": dst,
        "version": ver,
        "installedAt": installed_at,
        "lastUpdated": now,
    }]
    ok.append((name, ver))

io.open(REG_FILE, "w", encoding="utf-8").write(json.dumps(reg, ensure_ascii=False, indent=2))

print("\n已安装 %d / %d" % (len(ok), len(names)))
for n, v in ok:
    print("  OK  %-26s %s" % (n, v))
for f in fail:
    print("  FAIL", f)
print("\n注册表已更新：", REG_FILE)
