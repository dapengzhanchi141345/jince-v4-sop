#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""金策看板同步哨兵 (no_agent 确定性, 0 LLM, 每 10min):
根治「传不上就不管了」: 读 .last_synced stamp 与源看板 mtime 对比,
  ① 已同步且无更新          -> 静默退出(0 输出)
  ② 有更新待推且能推上去    -> 推成功 + 静默
  ③ 有更新但全路推不上      -> 投群点名(绝不静默吞失败)

[2026-10-20 根治 v2 · L1 落地] 旧版故障根因: 本地 git 仓 C:/Users/ASUS/jince-dashboard
双向分叉(落后远端 ~3093 + 领先 466 个从没推出去的"看板刷新" commit), 旧 7 条 git push 路
结构性永远非快进被拒, 却把 rejected 误报成"443 墙全挂"(真因是分叉不是墙).
根治: 主路改成 git 数据 API 四段远端重组(blobs->trees->commits->refs), 彻底不依赖本地仓,
非 force, 每次重取远端 HEAD/tree 重绑(不与并行推 tick_live.json 的进程抢 ref, 撞了新 head 就重算重试).
git 裸 push 降为最后兜底(分叉场景基本必拒, 留给将来分叉被解/干净克隆时). 删 443 墙误报文案.
看板 ~2MB: 不用 Contents API(单文件 100KB 上限会 413), 走 git 数据 API(100MB 上限).
只碰推送逻辑, 不碰挂单/撤单/任何交易配置, 不动本地仓 git 状态.
GBK 安全: 日志纯 ASCII, 投群消息中文(投群走 UTF-8 管道, 不受 GBK 影响).
"""
import os, json, base64, time, subprocess, tempfile, datetime
_HIDE = 0x08000000 if __import__("os").name == "nt" else 0  # CREATE_NO_WINDOW [后台化: gh/git/curl 子进程不闪窗]

SRC = r"E:\GoldstrategyEngine\data\daily_dashboard.html"
REPO = r"C:\Users\ASUS\jince-dashboard"   # 仅作本地 stamp 存放 + 兜底 git cwd, 主路不进 git
STAMP = os.path.join(REPO, ".last_synced")
GH_USER_REPO = "dapengzhanchi141345/jince-trading-dashboard"  # 用于 API 路径(不带 .git)


def gh(method, path, payload=None, timeout=300):
    """gh api 统一薄封装. payload 走临时 JSON --input(命令行内联 2MB 会炸), 返回 (rc, stdout, stderr)."""
    cmd = ["gh", "api", "-H", "User-Agent: jince-sync-guard-v2"]
    if payload is not None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(payload, f)
            inp = f.name
        cmd += ["-X", method, "--input", inp, path]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, creationflags=_HIDE)
        os.unlink(inp)
    else:
        cmd += [path]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, creationflags=_HIDE)
    return p.returncode, p.stdout, p.stderr


def git_push_fallback(timeout=90):
    """最后兜底: git 裸 push(系统 DNS). 双向分叉场景基本必拒, 留给干净克隆/分叉被解时."""
    try:
        p = subprocess.run(["git", "push", "origin", "main"], cwd=REPO,
                           capture_output=True, text=True, timeout=timeout, creationflags=_HIDE)
        return p.returncode == 0
    except subprocess.TimeoutExpired:
        return False


def api_push_index(retries=3):
    """主路: git 数据 API 四段远端重组, 把 SRC 作为 index.html 推上远端 main.
    不依赖本地仓 git 状态, 非 force. 每次重取远端 HEAD + 现 tree 重绑(不与并行推
    tick_live.json 的进程抢 ref; refs PUT 撞新 head 就下轮基于新 head 重算). 返回 (ok, 描述)."""
    # ① blob: SRC -> git/blobs (内容定, 只传一次; 2MB 在 git 数据 API 100MB 限内)
    try:
        b64 = base64.b64encode(open(SRC, "rb").read()).decode()
    except Exception as ex:
        return False, f"读源看板失败: {str(ex)[:120]}"
    rc, out, err = gh("POST", f"repos/{GH_USER_REPO}/git/blobs",
                      {"content": b64, "encoding": "base64"}, timeout=300)
    if rc != 0:
        return False, f"blob 上传失败: {(err.strip() or out.strip())[:140]}"
    blob_sha = json.loads(out)["sha"]

    last_err = ""
    for _ in range(retries):
        # ② 远端 HEAD + 现 tree (每次重取, 基于最新 head 重绑, 规避与 tick_live 抢 ref)
        rc, out, err = gh("GET", f"repos/{GH_USER_REPO}/git/ref/heads/main", timeout=60)
        if rc != 0:
            last_err = f"取远端 HEAD 失败: {(err.strip() or out.strip())[:100]}"
            time.sleep(2)
            continue
        head = json.loads(out)["object"]["sha"]
        rc, out, err = gh("GET", f"repos/{GH_USER_REPO}/git/trees/{head}", timeout=60)
        if rc != 0:
            last_err = f"取远端 tree 失败: {(err.strip() or out.strip())[:100]}"
            time.sleep(2)
            continue
        tj = json.loads(out)
        if tj.get("truncated"):
            last_err = "远端 tree 超 100 entries 无法全量重组"
            break
        entries = [e for e in tj.get("tree", []) if e.get("path") != "index.html"]
        entries.append({"path": "index.html", "mode": "100644", "type": "blob", "sha": blob_sha})
        # ③ 新 tree (只改 index.html, 其余含 tick_live.json 全保留原 sha)
        rc, out, err = gh("POST", f"repos/{GH_USER_REPO}/git/trees", {"tree": entries}, timeout=120)
        if rc != 0:
            last_err = f"建远端 tree 失败: {(err.strip() or out.strip())[:140]}"
            time.sleep(2)
            continue
        tree_sha = json.loads(out)["sha"]
        # ④ commit (parent = 远端 HEAD, 非 force)
        msg = f"auto: 看板刷新 {datetime.datetime.now():%m-%d %H:%M} (api 直推)"
        rc, out, err = gh("POST", f"repos/{GH_USER_REPO}/git/commits",
                          {"message": msg, "tree": tree_sha, "parents": [head]}, timeout=120)
        if rc != 0:
            last_err = f"建远端 commit 失败: {(err.strip() or out.strip())[:140]}"
            time.sleep(2)
            continue
        new_commit = json.loads(out)["sha"]
        # ⑤ 推 main 指针 (非 force; 撞 tick_live 新 head -> 下轮重取重算, 故再试)
        rc, out, err = gh("PUT", f"repos/{GH_USER_REPO}/git/refs/heads/main",
                          {"sha": new_commit}, timeout=60)
        if rc == 0:
            return True, "API 四段直推(blobs->trees->commits->refs, 不依赖本地仓)"
        last_err = f"推 main 指针失败/撞新 head: {(err.strip() or out.strip())[:140]}"
        time.sleep(2)
    return False, last_err


def main():
    now = datetime.datetime.now()
    if not os.path.exists(SRC):
        print("[看板哨兵-报警] 源文件不存在: " + SRC)
        return
    mtime = os.path.getmtime(SRC)
    last = 0.0
    if os.path.exists(STAMP):
        try:
            last = float(open(STAMP).read().strip())
        except Exception:
            last = 0.0
    if mtime <= last:
        return  # 已同步且无更新 -> 静默
    # 有更新待推: API 主路 -> git 兜底
    ok, how = api_push_index()
    if not ok and git_push_fallback():
        ok, how = True, "git 裸推(兜底)"
    if ok:
        open(STAMP, "w").write(str(mtime))
        return  # 推成功 -> 静默
    # 全路推不上 -> 投群点名(带待推内容时间戳, 供人工核验; 不再误报 443 墙)
    pending_since = time.strftime("%m-%d %H:%M:%S", time.localtime(mtime))
    last_ok = time.strftime("%m-%d %H:%M:%S", time.localtime(last)) if last > 1_000_000_000 else "无记录"
    print(f"【金策看板同步失败】{now:%m-%d %H:%M} 远端未更新")
    print(f"  · 本地看板已生成于 {pending_since} (mtime 戳), 待推")
    print(f"  · 上次成功推送: {last_ok}")
    print(f"  · 全路推不上: {how}")
    print(f"  · 公网页仍显示 {last_ok} 的旧数据; 主路=api.github.com(非 git 协议, 不受 443 墙影响),"
          f" 查网络/gh 登录; 10min 后自动重试, 推上即消")


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        # 护栏: 异常也发声, 绝不静默吞
        print(f"【金策看板同步哨兵-异常】{datetime.datetime.now():%m-%d %H:%M} {str(ex)[:150]}")
