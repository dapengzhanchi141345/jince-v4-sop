# -*- coding: utf-8 -*-
"""金策·全部工作 GitHub 夜间同步 (确定性 0 LLM, gh api 绕 443 墙, 增量).
用法: python jince_github_sync.py all|jince-sass|jince-ledger
机制: 本地 git commit(有改动才提) -> gh api git/blobs(按内容sha256缓存, 只传变了的)
      -> git/trees(全量树一次POST) -> git/commits(parent=远端HEAD) -> git/refs(推分支, 非force)
      无改动 -> 静默跳过(只打一行'无新改动')。
覆盖: ① D:/jince_sass (金策·策略SaaS全量源码, 私有仓 jince-sass)
      ② E:/workbuddy/金策宗师团 工作台账镜像仓 jince-ledger (状态卡/纪律卡/研究台账/引擎决策json)
"""
import subprocess, os, base64, json, sys, time, hashlib, datetime, shutil, glob, tempfile
_HIDE = 0x08000000 if __import__("os").name == "nt" else 0  # CREATE_NO_WINDOW [后台化: gh/git/curl 子进程不闪窗]

OWNER = "dapengzhanchi141345"
# [2026-11-03] gh 全路径解析: 会话 PATH 可能没 gh(旧PATH) → WinError 2; 绝对路径兜底(认证仍需 token)
_gh_full = r"C:\Users\Administrator\ghbin\bin\gh.exe"
GH = _gh_full if os.path.exists(_gh_full) else "gh"
CACHE_DIR = os.environ.get("TEMP", r"C:\Users\ASUS\AppData\Local\Temp")
LOG = os.path.join(tempfile.gettempdir(), "jince_gh_sync.log")


def gh(args, payload=None, timeout=180):
    cmd = [GH, "api", "-H", "User-Agent: jince-gh-sync"]
    if payload is not None:
        cmd += ["-X", "POST", "--input", "-", args]
        p = subprocess.run(cmd, input=json.dumps(payload), capture_output=True, text=True, timeout=timeout, creationflags=_HIDE)
    else:
        p = subprocess.run(cmd + [args], capture_output=True, text=True, timeout=timeout, creationflags=_HIDE)
    return p.returncode, p.stdout, p.stderr


def retry(fn, tries=5, backoff=3):
    last = None
    for i in range(tries):
        last = fn()
        if last[0] == 0:
            return last
        time.sleep(backoff * (i + 1))
    return last


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git(*args, cwd):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=300, creationflags=_HIDE)
    return r.returncode, r.stdout, r.stderr


def tracked_with_hash(dirpath, excludes=()):
    # 字节模式 ls-files -z: git 输出 UTF-8 路径字节, 手动解码。
    # (旧版 text=True 在 Windows 按 GBK 解码, 中文目录名乱码 -> os.path.exists 失败 -> 0 文件 -> 空树 422)
    r = subprocess.run(["git", "-c", "core.quotepath=0", "ls-files", "-z"],
                       cwd=dirpath, capture_output=True, timeout=300, creationflags=_HIDE)
    if r.returncode != 0:
        return None
    res = {}
    for raw in r.stdout.split(b"\0"):
        if not raw:
            continue
        p = raw.decode("utf-8", "replace")
        if any(p.startswith(e) or ("/" + e.rstrip("/")) in p for e in excludes):
            continue  # 排除前缀(如 vendor/ 上游submodule, 非本仓代码)
        fp = os.path.join(dirpath, p)
        if os.path.exists(fp) and not os.path.isdir(fp):
            res[p] = sha256_file(fp)
    return res


def build_nested_trees(full, files, cache):
    """自底向上建 GitHub 嵌套 tree: 每个目录一次 POST, 子目录先建拿 sha, 父树引用(mode 040000).
    GitHub git/trees 不接受跨层斜杠路径, 必须自底向上。
    files: {相对路径(带/): 内容sha256}; cache: {f"h:{sha256}": blob_sha}. 返回 (root_sha, err)."""
    bsha = {p: cache.get(f"h:{h}") for p, h in files.items()}
    missing = [p for p in files if not bsha[p]]
    if missing:
        return None, f"{len(missing)} 文件blob缺失(超100MB?): {missing[:5]}"
    dir_files = {}   # dir -> {直接文件名: blob_sha}
    dir_subs = {}    # dir -> {直接子目录名}
    for p in files:
        d, name = p.rsplit("/", 1) if "/" in p else ("", p)
        dir_files.setdefault(d, {})[name] = bsha[p]
        parts = p.split("/")
        for i in range(1, len(parts)):  # 每层目录登记进其父目录 (修顶层漏注册)
            parent = "/".join(parts[:i - 1]) if i >= 2 else ""
            dir_subs.setdefault(parent, set()).add(parts[i - 1])
    all_dirs = set(dir_files) | set(dir_subs) | {""}
    depth = lambda d: (d.count("/") if d else -1)  # 根=-1永远最后建, 一级目录=0, 逐级+1 (自底向上)
    subtree = {}
    for d in sorted(all_dirs, key=depth, reverse=True):
        entries = [{"path": n, "mode": "100644", "type": "blob", "sha": s}
                   for n, s in dir_files.get(d, {}).items()]
        for sub in sorted(dir_subs.get(d, set())):
            subfull = sub if d == "" else f"{d}/{sub}"
            if subtree.get(subfull):
                entries.append({"path": sub, "mode": "040000", "type": "tree", "sha": subtree[subfull]})
        rc, out, err = retry(lambda: gh(f"repos/{full}/git/trees", {"tree": entries}))
        if rc != 0:
            return None, f"tree失败@{d!r}: {err.strip()[:160]}"
        subtree[d] = json.loads(out)["sha"]
    root = subtree.get("")
    if not root:
        return None, "根tree未生成"
    return root, None


def push_via_api(dirpath, repo, branch, tag, excludes=()):
    """把 dirpath 的 git 跟踪文件推到 github O/repo 的 branch. 返回 (changed, err)"""
    full = f"{OWNER}/{repo}"
    cache_f = os.path.join(CACHE_DIR, f"jince_gh_cache_{repo}.json")
    cache = {}
    if os.path.exists(cache_f):
        try:
            cache = json.load(open(cache_f, encoding="utf-8"))
        except Exception:
            cache = {}
    files = tracked_with_hash(dirpath, excludes)
    if files is None:
        return 0, "git ls-files 失败(目录不是git仓)"
    # ① blob: 只传内容哈希未缓存的
    to_upload = [p for p, h in files.items() if f"h:{h}" not in cache]
    if to_upload:
        import concurrent.futures, threading
        cache_lk = threading.Lock()  # 竞态修(11-15): up() 写 cache 与 work() json.dump(cache) 迭代并发 -> dict size changed
        def up(p):
            b64 = base64.b64encode(open(os.path.join(dirpath, p), "rb").read()).decode()
            rc, out, err = retry(lambda: gh(f"repos/{full}/git/blobs", {"content": b64, "encoding": "base64"}))
            if rc != 0:
                return None
            blob_sha = json.loads(out)["sha"]
            with cache_lk:
                cache[f"h:{sha256_file(os.path.join(dirpath, p))}"] = blob_sha
            return p
        lk = threading.Lock()
        done = 0

        def work(p):
            nonlocal done
            r = up(p)
            with lk:
                done += 1
                if done % 100 == 0:
                    with cache_lk:
                        json.dump(cache, open(cache_f, "w", encoding="utf-8"))
                    print(f"  [{tag}] blob {done}/{len(to_upload)}", flush=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            list(ex.map(work, to_upload))
        with cache_lk:
            json.dump(cache, open(cache_f, "w", encoding="utf-8"))
    # ② 远端 HEAD: 空仓/分支不存在 → parents 置空(首笔提交, 推 ref 即建仓+建默认分支); 否则拿 HEAD
    rc, out, err = gh(f"repos/{full}/git/ref/heads/{branch}")
    if rc == 0:
        head = json.loads(out)["object"]["sha"]
        parents = [head]
    else:
        # 空仓: git 数据 API 对完全空仓全 409("Git Repository is empty"), 唯一解锁路 = Contents API 造首笔提交
        # (git blobs/trees/commits/refs 全废, 只有 Contents 能造出第一笔提交并建默认分支)
        seed_b64 = base64.b64encode(b"auto-seed").decode()
        rc2, out2, err2 = gh(f"repos/{full}/contents/.jince_seed",
                             {"message": "seed", "content": seed_b64, "encoding": "base64"})
        if rc2 == 0 and ("sha" in out2 or "commit" in out2):
            # Contents 成功 -> git 数据 API 解锁 -> 重新读 HEAD(现在是 seed 提交)当 parent
            rc3, out3, err3 = gh(f"repos/{full}/git/ref/heads/{branch}")
            head = json.loads(out3)["object"]["sha"] if rc3 == 0 else None
            parents = [head] if head else []
            print(f"  [{tag}] 空仓 -> Contents 播种成功, git 已解锁", flush=True)
        else:
            # Contents 也 404 = GitHub git 后端还没落地(建仓后异步开通) -> 明确报错让 cron 下轮重试
            return 0, f"空仓 Contents 播种未成(git后端未落地, 下轮cron自动重试): {(err2.strip() or out2.strip())[:120]}"
    # ③ 嵌套全量树 (自底向上建子目录树再引用; 被删文件自然不在)
    tree_sha, terr = build_nested_trees(full, files, cache)
    if terr:
        return 0, terr
    # ④ commit + 推 ref (非force; 若远端落后本地则fast-forward自然过)
    msg = f"auto-sync {tag} {datetime.datetime.now():%Y-%m-%d %H:%M} ({len(files)} files)"
    rc, out, err = retry(lambda: gh(f"repos/{full}/git/commits", {"message": msg, "tree": tree_sha, "parents": parents}))
    if rc != 0:
        return 0, f"commit失败: {err.strip()[:200]}"
    csha = json.loads(out)["sha"]
    rc, out, err = retry(lambda: gh(f"repos/{full}/git/refs/heads/{branch}", {"sha": csha}))
    if rc != 0:
        return 0, f"ref失败: {err.strip()[:200]}"
    print(f"  [{tag}] commit {csha[:10]} 已推 {full} ({branch}), {len(files)} 文件", flush=True)
    return len(to_upload), None


def local_commit(dirpath, tag):
    rc, out, err = git("add", "-A", cwd=dirpath)
    rc2, out2, err2 = git("commit", "-m", f"{tag} 自动同步前提交 {datetime.datetime.now():%Y-%m-%d %H:%M}", cwd=dirpath)
    return rc2 == 0, out2


def sync_jince_sass():
    tag = "jince-sass"
    d = r"D:\jince_sass"
    rc, out, err = git("status", "--porcelain", cwd=d)
    dirty = bool(out.strip())
    if dirty:
        ok, _ = local_commit(d, tag)
        if not ok:
            return False, "本地提交失败"
    else:
        # 无新改动: 远端已是最新(前夜推过)则跳过
        rc, out, err = git("log", "-1", "--format=%H", cwd=d)
        print(f"  [{tag}] 无本地新改动", flush=True)
    return push_via_api(d, "jince-sass", "main", tag, excludes=("vendor/",))


LEDGER_SRC = [
    # (glob, 镜像内相对前缀)
    (r"E:\workbuddy\金策宗师团\*.md", "金策宗师团"),
    (r"E:\workbuddy\金策宗师团\chief\*.md", "金策宗师团/chief"),
    (r"E:\workbuddy\金策宗师团\strategy-rd\*.md", "金策宗师团/strategy-rd"),
    (r"E:\workbuddy\金策宗师团\risk-officer\*.md", "金策宗师团/risk-officer"),
    (r"E:\workbuddy\金策宗师团\ops-manager\*.md", "金策宗师团/ops-manager"),
]
LEDGER_FILES = [
    ("E:/GoldstrategyEngine/data/discussion_log.jsonl", "引擎决策/discussion_log.jsonl"),
    ("E:/GoldstrategyEngine/data/rd_queue.json", "引擎决策/rd_queue.json"),
    ("E:/GoldstrategyEngine/data/rd_ledger.json", "引擎决策/rd_ledger.json"),
    ("E:/GoldstrategyEngine/data/task_ledger.json", "引擎决策/task_ledger.json"),
    ("E:/GoldstrategyEngine/data/rd_decisions.json", "引擎决策/rd_decisions.json"),
    ("E:/GoldstrategyEngine/data/veto_log.json", "引擎决策/veto_log.json"),
    ("E:/GoldstrategyEngine/data/risk_state.json", "引擎决策/risk_state.json"),
    ("E:/GoldstrategyEngine/data/xau_break_cancel_gate.json", "引擎决策/xau_break_cancel_gate.json"),
    ("E:/workbuddy/金策宗师团/_github_mirror/jince-ledger/skills/mt5-manual-trading-practice/SKILL.md", "skills/mt5-manual-trading-practice/SKILL.md"),
    ("E:/workbuddy/金策宗师团/_github_mirror/jince-ledger/skills/mt5-manual-trading-practice/references/post_trade_report.md", "skills/mt5-manual-trading-practice/references/post_trade_report.md"),
]
MIRROR = r"E:\workbuddy\金策宗师团\_github_mirror\jince-ledger"


def sync_jince_ledger():
    tag = "jince-ledger"
    os.makedirs(MIRROR, exist_ok=True)
    if not os.path.exists(os.path.join(MIRROR, ".git")):
        subprocess.run(["git", "init", "-b", "main"], cwd=MIRROR, capture_output=True, text=True, creationflags=_HIDE)
        rc, out, err = git("config", "user.name", OWNER, cwd=MIRROR)
        rc, out, err = git("config", "user.email", "404280473@qq.com", cwd=MIRROR)
        # 仓不存在就建(私有); 台账镜像仓名 jince-work-ledger (旧 jince-ledger git后端冷却坏, 弃用)
        rc, out, err = gh(f"repos/{OWNER}/jince-work-ledger")
        if rc != 0:
            rc2, out2, err2 = gh("user/repos", {"name": "jince-work-ledger", "private": True,
                                                "description": "金策宗师团工作台账镜像(自动同步)"})
            if rc2 != 0:
                return False, f"建jince-ledger仓失败: {err2.strip()[:150]}"
    # 拷贝: 源 -> 镜像 (大文件>5MB跳过)
    copied = 0
    for pat, prefix in LEDGER_SRC:
        for f in glob.glob(pat):
            if os.path.getsize(f) > 5 * 1024 * 1024:
                continue
            dst = os.path.join(MIRROR, prefix, os.path.basename(f))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if not os.path.exists(dst) or os.path.getmtime(dst) < os.path.getmtime(f):
                shutil.copy2(f, dst)
                copied += 1
    for src, dstrel in LEDGER_FILES:
        if not os.path.exists(src):
            continue
        if os.path.getsize(src) > 5 * 1024 * 1024:
            continue
        dst = os.path.join(MIRROR, dstrel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if not os.path.exists(dst) or os.path.getmtime(dst) < os.path.getmtime(src):
            shutil.copy2(src, dst)
            copied += 1
    if copied:
        ok, _ = local_commit(MIRROR, tag)
        if not ok:
            print(f"  [{tag}] 拷贝{copied}个但提交失败(可能无内容差异)", flush=True)
    else:
        print(f"  [{tag}] 台账无本地变化", flush=True)
        # 确认远端已推过(有 main commit); 空仓/没推过则强制推一次, 别把空仓当最新
        rc, out, err = gh(f"repos/{OWNER}/jince-work-ledger/git/ref/heads/main")
        if rc != 0:
            print(f"  [{tag}] 远端无 main(空仓或没推过), 强制推一次", flush=True)
            return push_via_api(MIRROR, "jince-work-ledger", "main", tag)
        return True, None
    return push_via_api(MIRROR, "jince-work-ledger", "main", tag)


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else "all"
    results = {}
    t0 = time.time()
    if only in ("all", "jince-sass"):
        ch, err = sync_jince_sass()
        results["jince-sass"] = ("OK" if err is None else f"FAIL {err}")
    if only in ("all", "jince-ledger"):
        ok, err = sync_jince_ledger()
        results["jince-ledger"] = ("OK" if ok else f"FAIL {err}")
    line = "GitHub夜间同步: " + " | ".join(f"{k} {v}" for k, v in results.items()) + f" | 用时{int(time.time()-t0)}s"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(datetime.datetime.now().isoformat() + " " + line + "\n")
    if any(v.startswith("FAIL") for v in results.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
