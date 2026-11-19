# -*- coding: utf-8 -*-
"""Hermes 全技能 GitHub 同步: default skills/ + 28 个专家 profile 的 skills/ -> hermes-skills(私有仓).
复用金策已验证的 push_via_api (gh api 绕 443 墙 + 内容sha256缓存去重 + 全量树一次POST + 非force推ref).
机制: 建镜像git仓(拷default skills到根, 各profile skills到profiles/<名>/, 过滤垃圾) -> git commit
      -> push_via_api(mirror, "hermes-skills", "main", "skills"). 远端已有的 .gitignore/.curator_ledger.jsonl 保留.
排除: .curator_backups/ __pycache__/ .venv/ *.pyc .git/ (垃圾, 非技能本体).
用法: python skills_github_sync.py
"""
import os, sys, glob, shutil, subprocess, json, time, datetime
_HIDE = 0x08000000 if __import__("os").name == "nt" else 0  # CREATE_NO_WINDOW [后台化: gh/git/curl 子进程不闪窗]

sys.path.insert(0, r"E:\workbuddy\国外模型\hermes\scripts")
from jince_github_sync import push_via_api, OWNER, gh, retry  # noqa: E402

HERMES = r"E:\workbuddy\国外模型\hermes"
MIRROR = os.path.join(HERMES, "_skills_mirror")
DEFAULT_SKILLS = os.path.join(HERMES, "skills")
PROFILES = os.path.join(HERMES, "profiles")
REPO = "hermes-skills"
# [2026-10-26] .hub/ = hermes 运行时技能索引缓存(如 .hub/index-cache/hermes-index.json ~50MB),
# 本地运行时产物, 非技能本体, 不进 Git 镜像(和 .curator_backups 同级). 旧版漏排除导致 49MB blob 推 GitHub 崩整仓.
JUNK = (".curator_backups", "__pycache__", ".venv", ".git", "node_modules", ".hub")


def is_junk(relpath):
    parts = relpath.replace("\\", "/").split("/")
    if any(p in JUNK for p in parts[:-1]):
        return True
    return relpath.endswith(".pyc")


def git(*args, cwd):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=300, creationflags=_HIDE)
    return r.returncode, r.stdout, r.stderr


def copy_into(src, dst_root):
    """把 src 目录(不含自身名)拷到 dst_root, 过滤垃圾. 返回文件数."""
    n = 0
    if not os.path.isdir(src):
        return 0
    for dirpath, dirnames, filenames in os.walk(src):
        # 原地剪垃圾子目录
        dirnames[:] = [d for d in dirnames if d not in JUNK]
        for fn in filenames:
            if fn.endswith(".pyc") or fn == ".git":
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, os.path.dirname(src))  # src 的父 作为基准
            # 相对到镜像根: src 下内容 -> dst_root 下同名
            sub = os.path.relpath(full, src)
            dst = os.path.join(dst_root, sub)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if not os.path.exists(dst) or os.path.getsize(dst) != os.path.getsize(full) \
               or os.path.getmtime(dst) < os.path.getmtime(full) - 1:
                shutil.copy2(full, dst)
            n += 1
    return n


def main():
    # ① 建镜像 git 仓
    if not os.path.exists(os.path.join(MIRROR, ".git")):
        os.makedirs(MIRROR, exist_ok=True)
        git("init", "-b", "main", cwd=MIRROR)
    for k, v in (("user.name", OWNER), ("user.email", "404280473@qq.com")):
        git("config", k, v, cwd=MIRROR)

    t0 = time.time()
    # ② 保留远端根级 infra (.gitignore / .curator_ledger.jsonl), 避免全量树 POST 误删
    for root_file in (".gitignore", ".curator_ledger.jsonl"):
        rc, out, err = gh(f"repos/{OWNER}/{REPO}/contents/{root_file}")
        if rc == 0:
            try:
                import base64
                data = base64.b64decode(json.loads(out).get("content", "")).decode("utf-8", "replace")
                open(os.path.join(MIRROR, root_file), "w", encoding="utf-8").write(data)
                print(f"  保留远端 {root_file}", flush=True)
            except Exception as e:
                print(f"  {root_file} 取不到, 跳过 ({e})", flush=True)
    if not os.path.exists(os.path.join(MIRROR, ".gitignore")):
        open(os.path.join(MIRROR, ".gitignore"), "w", encoding="utf-8").write(
            "node_modules/\n__pycache__/\n*.pyc\n.venv/\n.DS_Store\n")

    # ③ 拷 default skills/ -> 镜像根
    n_default = copy_into(DEFAULT_SKILLS, MIRROR)
    print(f"  default skills -> 根: {n_default} 文件", flush=True)

    # ④ 拷 各 profile skills/ -> 镜像 profiles/<名>/
    n_prof = 0
    prof_dirs = sorted(glob.glob(os.path.join(PROFILES, "*", "skills")))
    for pd in prof_dirs:
        pname = os.path.basename(os.path.dirname(pd))
        if pname.startswith("_") or pname in JUNK:
            continue
        dst = os.path.join(MIRROR, "profiles", pname)
        cnt = copy_into(pd, dst)
        if cnt:
            n_prof += cnt
            print(f"  profiles/{pname}: {cnt} 文件", flush=True)
    print(f"  合计: default {n_default} + profiles {n_prof} = {n_default + n_prof} 文件", flush=True)

    # ⑤ 本地 commit
    git("add", "-A", cwd=MIRROR)
    rc, out, err = git("commit", "-m", f"skills 全量同步(default+{len(prof_dirs)}profile) "
                                       f"{datetime.datetime.now():%Y-%m-%d %H:%M}", cwd=MIRROR)
    if rc != 0:
        print("  commit:", (out + err)[:200], flush=True)

    # ⑥ gh api 推
    ch, e = push_via_api(MIRROR, REPO, "main", "skills",
                         excludes=(".curator_backups/", "__pycache__/", ".venv/", ".hub/",
                                  ".hub/index-cache/"))
    if e:
        print(f"[skills] FAIL: {e}", flush=True)
        sys.exit(1)
    print(f"[skills] 已推 {OWNER}/{REPO} main, 本轮新传 {ch} blob, 用时 {int(time.time() - t0)}s", flush=True)


if __name__ == "__main__":
    main()
