# Git Data API 推送代码骨架（实战验证）

从「数千文件目录→GitHub 私有仓、git 协议被墙、可断点续传」场景提炼。各片段可独立复用；组合时保持 SKILL.md 流程顺序。

## 1) api()：DNS 抖动容忍 + 网络重试（HTTP 状态码不重试）
```python
import json, time, urllib.request, urllib.error
API = "https://api.github.com"  # 拼接用 API + "/" + path，勿漏斜杠

def api(method, path, payload=None):
    url = API + ("/" + path if not path.startswith("/") else path)
    for attempt in range(30):
        try:
            data = json.dumps(payload).encode() if payload is not None else None
            req = urllib.request.Request(url, data=data, method=method,
                headers={"Authorization": f"token {TOKEN}", "User-Agent": "bulk-push",
                         "Accept": "application/vnd.github+json"})
            r = urllib.request.urlopen(req, timeout=120)
            return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()          # HTTP 层: 不重试, 交给调用方判断
        except Exception:
            time.sleep(10)                    # 网络/DNS 层: 重试 (GFW 下 getaddrinfo 偶发失败)
    return -1, b""
# DNS 不稳时: socket.getaddrinfo hook 把 api.github.com pin 到 DoH 解析出的 IP, 定期刷新
```

## 2) git blob SHA1（缓存键 + 对账基准）
```python
import hashlib, os
def git_blob_sha1(fp):
    h = hashlib.sha1(b"blob %d\x00" % os.path.getsize(fp))
    h.update(open(fp, "rb").read())
    return h.hexdigest()
```

## 3) blob 上传 + 内容缓存（断点续传核心）
```python
CACHE = json.load(open(CACHE_F, encoding="utf-8")) if os.path.exists(CACHE_F) else {}

def blob_for(repo, fp):
    s1 = git_blob_sha1(fp)
    key = f"{repo}:{s1}"
    if CACHE.get(key):
        return CACHE[key]
    b64 = base64.b64encode(open(fp, "rb").read()).decode()
    for i in range(5):                        # 400 = 偶发 malformed, 重提; 其它码不重试
        st, body = api("POST", f"repos/{OWNER}/{repo}/git/blobs",
                       {"content": b64, "encoding": "base64"})
        if st in (200, 201):
            CACHE[key] = json.loads(body)["sha"]
            return CACHE[key]
        if st != 400:
            raise RuntimeError(f"blob {os.path.basename(fp)}: {st} {body[:150]!r}")
        time.sleep(10)
    raise RuntimeError(f"blob 400 x5 {os.path.basename(fp)}")
# 每 30 个上传原子保存一次 CACHE (写临时文件再 rename), 被杀也不丢进度
```

## 4) 建树器（关键：中间目录登记，off-by-one 会静默丢整支子树）
```python
def make_dir_map(final_paths):
    """final_paths = {"a/b/c.py": blob_sha, ...}; 返回 {目录: {名字: (mode, sha)}}"""
    dir_map = {}
    for p in final_paths:
        parts = p.split("/")
        d = "" if len(parts) == 1 else "/".join(parts[:-1])
        dir_map.setdefault(d, {})[parts[-1]] = ("100644", final_paths[p])
        for i in range(1, len(parts)):        # 注意: 是 len(parts) 不是 len(parts)-1!
            parent = "/".join(parts[:i-1]) if i >= 2 else ""
            dir_map.setdefault(parent, {})[parts[i-1]] = ("040000", None)
    return dir_map

def build_trees(repo, dir_map):
    dir_files, dir_subs, subtree = {}, {}, {}
    for d, m in dir_map.items():
        for name, (mode, sha) in m.items():
            if mode == "040000":
                dir_subs.setdefault(d, set()).add(name)
            else:
                dir_files.setdefault(d, {})[name] = sha
    depth = lambda d: (d.count("/") if d else -1)
    root = None
    for d in sorted(set(dir_files) | set(dir_subs) | {""}, key=depth, reverse=True):  # 深→浅
        entries = [{"path": n, "mode": "100644", "type": "blob", "sha": s}
                   for n, s in sorted(dir_files.get(d, {}).items())]
        for sub in sorted(dir_subs.get(d, set())):
            subfull = sub if d == "" else f"{d}/{sub}"
            if subfull in subtree:                                # 子树已建才挂引用
                entries.append({"path": sub, "mode": "040000", "type": "tree", "sha": subtree[subfull]})
        if not entries:
            continue
        st, body = api("POST", f"repos/{OWNER}/{repo}/git/trees", {"tree": entries})
        if st not in (200, 201):
            raise RuntimeError(f"tree @{d!r}: {st} {body[:200]!r}")   # 422 = 条目过多, 见 SKILL.md
        subtree[d] = json.loads(body)["sha"]
        if d == "":
            root = subtree[""]
    if not root:
        raise RuntimeError("根 tree 未生成")
    return root
# 上线前离线自检: 用假 api() 记录 POST, 断言父树含子目录引用、根树含全部一级子目录
```

## 5) 新仓 seed / provisioning 轮询
```python
def ensure_repo(name):
    st, _ = api("GET", f"/repos/{OWNER}/{name}")
    if st == 404:
        api("POST", f"/user/repos", {"name": name, "private": True, "auto_init": False})
    if api("GET", f"repos/{OWNER}/{name}/git/ref/heads/main")[0] == 200:
        return                                   # 已有 main, 直接推
    for i in range(60):                          # 60x45s ≈ 45 分钟/job; 超了不删仓, 下轮再探
        st, body = api("PUT", f"repos/{OWNER}/{name}/contents/README.md",
                       {"branch": "main", "message": "seed",
                        "content": base64.b64encode(b"placeholder\n").decode()})
        if st in (200, 201):
            return                                # provisioning 落地
        if st != 404:
            raise RuntimeError(f"seed 异常 {st} {body[:150]!r}")
        time.sleep(45)
    raise RuntimeError(f"{name} provisioning 未落地, 稍后重探 (勿删仓重建)")
# 空窗 30~90+ 分钟正常; 轮询间隙手动 curl 一次 seed PUT 可提前解锁
```

## 6) 并集 + 重锚修复
```python
def remote_map(repo, head=None):
    if head is None:
        st, body = api("GET", f"repos/{OWNER}/{repo}/git/ref/heads/main")
        head = json.loads(body)["object"]["sha"] if st == 200 else None
    if head is None:
        return {}, None
    st, body = api("GET", f"repos/{OWNER}/{repo}/git/trees/{head}?recursive=1")
    m = {e["path"]: e["sha"] for e in json.loads(body).get("tree", []) if e["type"] == "blob"}
    return m, head

# 修复坏推: st, b = api("GET", f"repos/{OWNER}/{repo}/commits/main")
# base = json.loads(b)["parents"][0]["sha"]   # 坏提交的父 = 最后一个好树
# push(..., base_ref=base) 时: commit parents=[base], ref 更新加 "force": True
# force 仅限这次自我修复重锚; 共享/定时同步路径禁用 force
```

## 7) 推送 + 对账（完成判定）
```python
def push(repo, files, keep_remote_only=True, base_ref=None):
    rmap, head = remote_map(repo, head=base_ref)
    final = dict(rmap) if keep_remote_only else {}
    for rel, absp in files.items():
        final[rel] = blob_for(repo, absp)
    root = build_trees(repo, make_dir_map(final))
    csha = json.loads(api("POST", f"repos/{OWNER}/{repo}/git/commits",
        {"message": "backup", "tree": root, "parents": [head] if head else []})[1])["sha"]
    ref_payload = {"sha": csha}
    if base_ref:
        ref_payload["force"] = True              # 仅重锚修复
    st, body = api("POST", f"repos/{OWNER}/{repo}/git/refs/heads/main", ref_payload)
    if st not in (200, 201):
        raise RuntimeError(f"ref 更新 {st}")
    # 对账: 远端 blob 计数必须 == 本地期望 (本地 + 保留远端独有 [+ README seed])
    blobs = [e for e in json.loads(api("GET", f"repos/{OWNER}/{repo}/git/trees/main?recursive=1")[1])
             .get("tree", []) if e["type"] == "blob"]
    expected = len(files) + (sum(1 for p in rmap if p not in files) if keep_remote_only else 0) + 1
    assert len(blobs) == expected, f"远端 {len(blobs)} != 期望 {expected} -> 坏推, 未记账"
    return csha
```

## 8) 限流 + 台账
```python
def wait_for_rate(min_remaining=50):
    while True:
        st, b = api("GET", "/rate_limit")
        core = json.loads(b)["resources"]["core"]
        if core["remaining"] > min_remaining:
            return
        time.sleep(int(core["reset"] - time.time()) + 60)   # 睡到窗口重置, 不硬撞
# 完成台账: gh_push_completed.json = [已对账全绿的 repo]; 重启队列自动跳过; 坏推仓从台账移除重推
```
