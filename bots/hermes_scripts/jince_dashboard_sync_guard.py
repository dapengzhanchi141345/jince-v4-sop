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
REPO = os.environ.get("JINCE_DASH_REPO", r"E:\workbuddy\金策宗师团\_github_mirror\jince-dashboard")  # [2026-11-05] WinError 267 根治: 本机无 C:\Users\ASUS\jince-dashboard → E 盘镜像+自创建
import os as _os; _os.makedirs(REPO, exist_ok=True)
STAMP = os.path.join(REPO, ".last_synced")
GH_USER_REPO = "dapengzhanchi141345/jince-trading-dashboard"  # 用于 API 路径(不带 .git)
# [2026-11-03] gh 全路径解析: 会话 PATH 可能没 gh(旧PATH) → WinError 2; 绝对路径兜底(认证仍需 token)
_gh_full = r"C:\Users\Administrator\ghbin\bin\gh.exe"
GH = _gh_full if os.path.exists(_gh_full) else "gh"


def gh(method, path, payload=None, timeout=300):
    """gh api 统一薄封装. payload 走临时 JSON --input(命令行内联 2MB 会炸), 返回 (rc, stdout, stderr)."""
    cmd = [GH, "api", "-H", "User-Agent: jince-sync-guard-v2"]
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
    """最后兜底: git 裸 push(系统 DNS). 双向分叉场景基本必拒, 留给干净克隆/分叉被解时.
    [2026-11-03 根治] 本地仓 REPO 不存在时直接跳过(不再 WinError 267 冒到哨兵), 并 catch OSError."""
    if not os.path.isdir(REPO):
        print(f"  · git 兜底跳过: 本地仓 {REPO} 不存在 (WinError 267 根治: 不碰无效 cwd)")
        return False
    try:
        p = subprocess.run(["git", "push", "origin", "main"], cwd=REPO,
                           capture_output=True, text=True, timeout=timeout, creationflags=_HIDE)
        return p.returncode == 0
    except subprocess.TimeoutExpired:
        return False
    except OSError as e:
        print(f"  · git 兜底 OSError: {e} (跳过, 不冒泡)")
        return False


# [2026-11-09 防刷屏] 与行情喂同族: gh 卡认证/extnet 断期间哨兵每 10min 灌同一条"全路推不上".
# 同一失败状态持续 -> 群每 2h 才重申一次(状态变/推活才即时报), 本地每拍全量留痕, 绝不静默吞.
_ANOM_STATE = r"E:\GoldstrategyEngine\data\dash_sync_anomaly_state.json"
_QUIET_LOG = r"E:\GoldstrategyEngine\data\dash_sync_quiet.jsonl"
_REMIND_SEC = 2 * 3600

def _anomaly_gate(detail):
    """返回 (是否投群, 同状态连续拍数). 首报/状态变/超 REMIND_SEC 才投群; 静默拍也计数留痕."""
    fp = detail[:60]
    st = {}
    try:
        st = json.load(open(_ANOM_STATE, encoding="utf-8"))
    except Exception:
        pass
    now_ts = time.time()
    changed = st.get("fingerprint") != fp
    stuck = 1 if (changed or not st) else st.get("stuck_count", 0) + 1
    should = changed or (now_ts - st.get("last_report_ts", 0) > _REMIND_SEC)
    json.dump({"fingerprint": fp, "last_report_ts": now_ts if should else st.get("last_report_ts", 0),
               "stuck_count": stuck}, open(_ANOM_STATE, "w", encoding="utf-8"), ensure_ascii=False)
    if not should:
        try:
            with open(_QUIET_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps({"t": int(now_ts), "ev": "quiet_beat", "kind": "dash_sync",
                                    "stuck": stuck, "note": detail[:80]}, ensure_ascii=False) + "\n")
        except Exception:
            pass
    return should, stuck

def _anomaly_clear():
    try:
        os.unlink(_ANOM_STATE)
    except OSError:
        pass


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
        _anomaly_clear()  # 推活 -> 清卡滞状态, 下次再坏=状态变化即时报
        return  # 推成功 -> 静默
    # 全路推不上 -> 投群点名(带待推内容时间戳, 供人工核验; 不再误报 443 墙)
    # [11-09 防刷屏] 同一失败状态持续 -> 群 2h 才重申, 静默拍本地留痕; 状态变/推活才即时报
    should, stuck = _anomaly_gate(how)
    if not should:
        return  # 静默拍: 本地看板照生成, 异常已报过 (dash_sync_quiet.jsonl 留痕)
    pending_since = time.strftime("%m-%d %H:%M:%S", time.localtime(mtime))
    last_ok = time.strftime("%m-%d %H:%M:%S", time.localtime(last)) if last > 1_000_000_000 else "无记录"
    print(f"【金策看板同步失败】{now:%m-%d %H:%M} 远端未更新")
    print(f"  · 本地看板已生成于 {pending_since} (mtime 戳), 待推")
    print(f"  · 上次成功推送: {last_ok}")
    print(f"  · 全路推不上: {how}")
    if stuck > 1:
        print(f"  · (连续 {stuck} 拍同状态, 群 2h 重申一次, 推上即消)")
    print(f"  · 公网页仍显示 {last_ok} 的旧数据; 主路=api.github.com(非 git 协议, 不受 443 墙影响), 查网络/gh 登录; 10min 后自动重试, 推上即消")


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        # 护栏: 异常也发声, 绝不静默吞
        print(f"【金策看板同步哨兵-异常】{datetime.datetime.now():%m-%d %H:%M} {str(ex)[:150]}")
