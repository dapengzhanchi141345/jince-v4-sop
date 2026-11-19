# -*- coding: utf-8 -*-
"""
sync_to_github.py — 金策引擎自动同步到 GitHub (jince-engine 私有仓)
====================================================================
设计:
  - 每次调用: 重新从 E:/GoldstrategyEngine 挑核心源码 → 脱敏(密码→占位符) →
    重打 AES-256 加密凭证包(密码141345, 每次调用重新生成确保最新) →
    git add/commit/push 到 C:/Users/ASUS/jince-engine。
  - 敏感凭证永远不进明文仓库, 只进加密包; 仓库里代码是脱敏版(占位符 __MT5_PASSWORD__)。
  - GitHub 在此网络被墙(20.205.x 通不了), 直连 known-good IP 140.82.113.4 +
    关证书校验(SNI 保留) 绕过; gh CLI 的 API 链路本身通, 但 git 走被墙 IP。
  - 失败不炸主循环: 任何异常 → 记日志 + 返回非 0, 调用方 fail-open。

用法:
  python sync_to_github.py            # 同步 + 提交 (默认分支 main)
  python sync_to_github.py --dry      # 只重挑+脱敏+加密, 不 commit/push, 打印将要改动
  python sync_to_github.py --message "升级: xxx"   # 自定义提交信息
"""
import os, sys, shutil, subprocess, time, json, hashlib, datetime
_HIDE = 0x08000000 if __import__("os").name == "nt" else 0  # CREATE_NO_WINDOW [后台化: gh/git/curl 子进程不闪窗]

# ===== 路径 =====
ROOT     = "E:/GoldstrategyEngine"                    # 源系统(活体)
REPO     = "C:/Users/ASUS/jince-engine"               # 本地 git 仓
ENCB     = "C:/Users/ASUS/jince_credentials_encrypted.zip"  # 加密凭证包(临时, 会拷进仓)
LOG      = "E:/GoldstrategyEngine/data/github_sync.log"
PY       = "C:/Users/ASUS/.workbuddy/binaries/python/envs/ate/Scripts/pythonw.exe"
GHPASS   = b"141345"      # 加密凭证包密码(持有者约定口令)
GH_USER  = "dapengzhanchi141345"
GH_REPO  = "jince-engine"
GH_IP    = "185.199.108.153" # known-good github Anycast IP (140.82.113.4 现不通, 换 185 段)

# 核心目录 + 排除(与首次上传一致)
CORE = {"multi_agent","engine","strategies","execution","risk","models","evolution",
        "integrations","tools","validation","deploy","archive","optimized","docs","enhancements"}
EXCL = {"backup","python","logs","data","ea4.3bao",".workbuddy",".git","__pycache__",
        ".pytest_cache","node_modules"}
EXT  = {".py",".md",".json",".csv",".txt",".bat",".cfg",".ini",".toml",".yaml",
        ".yml",".env",".ps1"}
PWRD   = ""            # 真实 MT5 交易密码(绝不进明文仓)
PLACE  = "__MT5_PASSWORD__"      # 仓库里的占位符

def log(msg):
    line = f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    print(line)
    try:
        with open(LOG, "a", encoding="utf-8") as f: f.write(line + "\n")
    except Exception:
        pass

def pick_core():
    """从 ROOT 挑核心源码, 脱敏, 写入 REPO(先清空重建, 保留 .git)。返回 (文件数, 脱敏数)。"""
    # 清空 REPO 工作区但保留 .git
    for dp, dn, fn in os.walk(REPO, topdown=False):
        for d in dn:
            if os.path.isdir(os.path.join(dp, d)) and ".git" not in dp.replace(REPO, "").lstrip("\\/"):
                pass
    # 更稳妥: 删掉除 .git 外所有
    for entry in os.listdir(REPO):
        p = os.path.join(REPO, entry)
        if entry == ".git": continue
        if os.path.isdir(p) and not os.path.islink(p): shutil.rmtree(p, ignore_errors=True)
        else: os.remove(p)

    n = 0; obsc = 0
    for dp, dn, fn in os.walk(ROOT):
        rel = os.path.relpath(dp, ROOT)
        top = rel.split(os.sep)[0] if rel != "." else "."
        dn[:] = [d for d in dn if d not in EXCL]
        for f in fn:
            ext = os.path.splitext(f)[1].lower()
            ok = (ext in EXT) and ((top == "." and rel == ".") or top in CORE)
            if not ok: continue
            p = os.path.join(dp, f); s = os.path.getsize(p)
            if s > 5*1024*1024: continue
            arc = rel + "/" + f if rel != "." else f
            dst = os.path.join(REPO, *arc.split("/"))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            data = open(p, "rb").read()
            if PWRD in data.decode("utf-8", "replace"):
                open(dst, "wb").write(data.replace(PWRD.encode(), PLACE.encode()))
                obsc += 1
            else:
                open(dst, "wb").write(data)
            n += 1
    # [2026-10-06] 看板网页纳入同步: 全链每30min重生成 daily_dashboard.html,
    # 一并 commit+push, 否则线上/公网页永远停在旧快照(它属 data/, 不在 CORE 里)
    dash = os.path.join(ROOT, "data", "daily_dashboard.html")
    if os.path.exists(dash):
        shutil.copy(dash, os.path.join(REPO, "dashboard.html"))
        n += 1
    return n, obsc

def make_encryption_pack():
    """重打 AES-256 加密凭证包(全部含密码的原始文件 + 账号/券商报告类), 拷进 REPO。返回文件数。"""
    import pyzipper
    S = "C:/Users/ASUS/jince-secrets-staging2"
    if os.path.exists(S): shutil.rmtree(S)
    # 1) 含真实密码的文件(原始, 不脱敏) → 包
    zfiles = []
    for dp, dn, fn in os.walk(ROOT):
        rel = os.path.relpath(dp, ROOT); top = rel.split(os.sep)[0] if rel != "." else "."
        dn[:] = [d for d in dn if d not in EXCL]
        for f in fn:
            ext = os.path.splitext(f)[1].lower()
            ok = (ext in EXT) and ((top == "." and rel == ".") or top in CORE)
            if not ok: continue
            p = os.path.join(dp, f)
            if os.path.getsize(p) > 5*1024*1024: continue
            txt = open(p, "rb").read().decode("utf-8", "replace")
            if PWRD in txt or "TradeMaxGlobal" in txt or "60137964" in txt or "60043976" in txt:
                arc = (rel + "/" + f) if rel != "." else f
                d = os.path.join(S, *arc.split("/")); os.makedirs(os.path.dirname(d), exist_ok=True)
                open(d, "wb").write(open(p, "rb").read()); zfiles.append(arc)
    # 2) 打包
    if os.path.exists(ENCB): os.remove(ENCB)
    files = sorted((os.path.join(dp, f),
                    os.path.relpath(os.path.join(dp, f), S).replace(os.sep, "/"))
                   for dp, dn, fn in os.walk(S) for f in fn)
    with pyzipper.AESZipFile(ENCB, "w", encryption=pyzipper.WZ_AES, compresslevel=9) as z:
        z.setpassword(GHPASS)
        for p, a in files: z.write(p, arcname=a)
    shutil.copy(ENCB, os.path.join(REPO, "jince_credentials_encrypted.zip"))
    return len(files)

# git 可执行路径（ate env PATH 里 git.EXE 大小写不定，显式指定）
import shutil as _shutil
GIT = _shutil.which("git") or r"E:\workbuddy\国外模型\hermes\git\mingw64\bin\git.EXE"

GIT_USER = "dapengzhanchi141345"
GIT_MAIL = "404280473@qq.com"

def git_commit(message):
    r = subprocess.run([GIT, "add", "-A"], cwd=REPO, capture_output=True, text=True, creationflags=_HIDE)
    st = subprocess.run([GIT, "diff", "--cached", "--quiet"], cwd=REPO, creationflags=_HIDE)
    if st.returncode == 0:
        log("无改动, 跳过 commit")
        return True
    r = subprocess.run([GIT, "-c", f"user.name={GIT_USER}", "-c", f"user.email={GIT_MAIL}",
                        "commit", "-m", message], cwd=REPO, capture_output=True, text=True, creationflags=_HIDE)
    if r.returncode != 0:
        log(f"commit 失败: {r.stderr[:300]}")
        return False
    return True

def _gh_token():
    """读 gh CLI 的 keyring token（本机已验活，走 github.com 标准 443 绕开被墙直连线）。
    实现: 调 `gh auth token`（不落盘）；失败返回 None。"""
    import shutil
    gh = shutil.which("gh") or r"C:\Users\ASUS\.bin\gh.exe"
    for cand in [gh, r"C:\Users\ASUS\.bin\gh.exe"]:
        if not cand:
            continue
        try:
            r = subprocess.run([cand, "auth", "token"], capture_output=True, text=True, timeout=30, creationflags=_HIDE)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
        except Exception:
            continue
    return None

def git_push():
    """双通道推送: ① gh token HTTPS(走 github.com 标准 443, gh 已验通) → ② known-good IP 直连兜底。
    2026-09-27: 直连 IP 线持续 Connection reset，gh token 通道验通可绕开。"""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    # 通道1: gh token
    tok = _gh_token()
    if tok:
        r = subprocess.run([GIT, "push",
                            f"https://x-access-token:{tok}@github.com/{GH_USER}/{GH_REPO}.git", "main"],
                           cwd=REPO, capture_output=True, text=True, env=env, creationflags=_HIDE)
        if r.returncode == 0:
            log("push OK via gh-token https")
            return True
        log(f"push gh-token 失败: {r.stderr[:200]}")
    # 通道2: gh-proxy.com 代理直推(绕 TLS 墙, 比 IP 直连稳). 环境变量 JINCE_GH_PROXY 指定代理.
    # 2026-10-06: IP 直连(185.199.108.x + http.<IP>.resolve) 在部分网络下 443 被墙,
    # 优先走 JINCE_GH_PROXY 代理(gh token 内嵌在通道3 URL 已认证); 无代理才回退 IP 直连.
    proxy = os.environ.get("JINCE_GH_PROXY", "").strip()
    remote = f"https://github.com/{GH_USER}/{GH_REPO}.git"
    env2 = {**os.environ, "GIT_SSL_NO_VERIFY": "1", "GIT_TERMINAL_PROMPT": "0"}
    if proxy:
        env2["https_proxy"] = proxy; env2["HTTPS_PROXY"] = proxy
        r = subprocess.run([GIT, "-c", "http.sslVerify=false", "push", remote, "main"],
                           cwd=REPO, capture_output=True, text=True, env=env2, creationflags=_HIDE)
        if r.returncode == 0:
            log(f"push OK via proxy {proxy[:30]}")
            return True
        log(f"push proxy 失败: {r.stderr[:200]}, 回退 IP 直连")
    # IP 直连兜底(保留域名 Host 头). 2026-10-06: 185 段 4 IP 常被墙, 加 140.82.113.4 兜底
    # (实测 140 通时 185 全断, 反之亦然, 两段轮换). 探活选通的 IP 推.
    import socket
    cands = [f"185.199.108.{153+i}" for i in range(4)] + ["140.82.113.4"]
    alive = []
    for ip in cands:
        try:
            s = socket.create_connection((ip, 443), timeout=3); s.close(); alive.append(ip)
        except Exception:
            pass
    if not alive:
        alive = cands  # 全断就按顺序全试(可能有瞬断)
    for ip in alive:
        resolve_cfg = f"http.{ip}.resolve=github.com:443:{ip}"
        r = subprocess.run([GIT, "-c", resolve_cfg, "-c", "http.sslVerify=false",
                            "push", remote, "main"], cwd=REPO,
                           capture_output=True, text=True, env=env2, creationflags=_HIDE)
        if r.returncode == 0:
            log(f"push OK (IP {ip} 直连)")
            return True
        log(f"push 失败: {ip} {r.stderr[:160]}")
        time.sleep(4)
    return False

def main():
    dry = "--dry" in sys.argv
    msg = "auto-sync"
    for a in sys.argv[1:]:
        if a.startswith("--message="): msg = a.split("=", 1)[1]
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    commit_msg = f"[金策引擎] 自动同步 {ts} - {msg}"
    try:
        n, obsc = pick_core()
        zc = make_encryption_pack()
        log(f"挑核心 {n} 文件, 脱敏 {obsc}, 加密包 {zc} 凭证")
        if dry:
            log("--dry 模式: 不 commit/push")
            return 0
        if not git_commit(commit_msg):
            log("commit 失败, 中止"); return 1
        if not git_push():
            log("push 全部失败(网络), 改动留在本地仓, 下次再推"); return 2
        log("同步成功 → github.com/dapengzhanchi141345/jince-engine")
        return 0
    except Exception as e:
        import traceback
        log(f"异常: {e}\n{traceback.format_exc()[:400]}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
