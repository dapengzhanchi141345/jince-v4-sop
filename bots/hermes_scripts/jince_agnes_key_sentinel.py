# -*- coding: utf-8 -*-
"""
jince_agnes_key_sentinel.py — Agnes key 每日哨 (no_agent cron, 00:05)
李彦明 11-14 key 固定分配后的自维护哨:
  ① 全量探针: 交易 5 席(主.cn+备.com) + 其他 26 席(各 1 把专属) + 池 17 把 + 孤儿 k10-8/k10-9
  ② 自动回收: k10-8/k10-9 从 429 堵墙恢复后, 自动挂进 default 的 fallback_providers 备链 (文本手术+解析验活)
  ③ 报障: 交易席 key 堵墙/死亡 = RED 一行; 其他席堵墙 = YEL 一行; 全绿 = 静默(无 stdout)
探针纪律: 一律 curl (urllib 在 .cn 301 重定向上丢 Authorization = 假 401); /models 200 是假阳性, 必须真发 chat 才算活。
留痕: E:\\GoldstrategyEngine\\data\\agnes_key_sentinel_last.json + task_ledger 追加 1 行。
"""
import json, os, re, subprocess, hashlib, sys, datetime

HERMES = r"E:\workbuddy\国外模型\hermes"
CN, COM = "https://api.agnes-ai.cn/v1", "https://apihub.agnes-ai.com/v1"
POOL_JSON = os.path.join(HERMES, "agnes_pool_keys.json")
LEDGER = r"E:\GoldstrategyEngine\data\task_ledger.json"
LAST = r"E:\GoldstrategyEngine\data\agnes_key_sentinel_last.json"
DEFAULT_CFG = os.path.join(HERMES, "config.yaml")


def fp(v):
    return hashlib.sha1(v.encode()).hexdigest()[:8]


def env_values(profile):
    """profile .env 里所有 *_KEY 值 {var: sk-...}"""
    f = ".env" if profile == "default" else os.path.join(HERMES, "profiles", profile, ".env")
    out = {}
    if not os.path.exists(f):
        return out
    for line in open(f, encoding="utf-8").read().splitlines():
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            n, v = s.split("=", 1)
            v = v.strip().strip('"').strip("'")
            if v.startswith("sk-"):
                out[n] = v
    return out


def block_info(cfg_text, block):
    """某 provider 块的 (base_url, key_env, inline_key) — 纯 regex"""
    m = re.search(r"(?m)^  " + re.escape(block) + r":\n", cfg_text)
    if not m:
        return None
    i = m.end()
    m2 = re.search(r"(?m)^(?:  [a-z0-9_-]+:|fallback_providers:|providers:|toolsets:|video_gen:|agent:|plugins:)", cfg_text[i:])
    seg = cfg_text[i:(i + m2.start()) if m2 else len(cfg_text)]
    bu = re.search(r"base_url:\s*(\S+)", seg)
    ke = re.search(r"key_env:\s*(\S+)", seg)
    ak = re.search(r"api_key:\s*(sk-\S+)", seg)
    return (bu.group(1) if bu else "", ke.group(1) if ke else "", ak.group(1) if ak else "")


def main_provider_chain(cfg_text):
    """(main_provider, [fb_providers...]) — 纯 regex"""
    mm = re.search(r"(?m)^model:\n", cfg_text)
    main = None
    if mm:
        i = mm.end()
        m2 = re.search(r"(?m)^\S", cfg_text[i:])
        seg = cfg_text[i:(i + m2.start()) if m2 else len(cfg_text)]
        pm = re.search(r"provider:\s*(\S+)", seg)
        main = pm.group(1) if pm else None
    fbs = []
    fm = re.search(r"(?m)^fallback_providers:\n?", cfg_text)
    if fm:
        i = fm.end()
        m2 = re.search(r"(?m)^\S", cfg_text[i:])
        seg = cfg_text[i:(i + m2.start()) if m2 else len(cfg_text)]
        fbs = re.findall(r"-\s*provider:\s*(\S+)", seg)
    return main, fbs


def probe(base, key):
    """curl 双探: /models(快速筛) + 真 chat(判活/判 429)"""
    def curl(url, extra, tmo):
        try:
            r = subprocess.run(["curl", "-sS", "--noproxy", "*", "--max-time", str(tmo),
                                "-w", "\\n%{http_code}", url, "-H", f"Authorization: Bearer {key}"] + extra,
                               capture_output=True, text=True, timeout=tmo + 10)
            out = r.stdout
            code = out.rsplit("\n", 1)[-1].strip()
            body = out.rsplit("\n", 1)[0]
            return code, body
        except Exception as e:
            return "ERR", str(e)[:80]

    c1, _ = curl(base + "/models", [], 15)
    if c1 == "401":
        return "DEAD"  # 端点不认这把 key (配置错配)
    payload = json.dumps({"model": "agnes-3.0-flash", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 4})
    c2, b2 = curl(base + "/chat/completions",
                  ["-H", "Content-Type: application/json", "-d", payload], 25)
    if c2 == "200" and ("choices" in b2 or "content" in b2):
        return "LIVE"
    if c2 == "429":
        return "WALL"
    return f"DEAD({c2})"


def add_to_default_fallback(block):
    """把 block 追加进 default config 的 fallback_providers (幂等) + pyyaml 验活"""
    t = open(DEFAULT_CFG, encoding="utf-8").read()
    if re.search(r"(?m)^\s*-\s*provider:\s*" + re.escape(block) + r"\s*$", t):
        return "already"
    fm = re.search(r"(?m)^fallback_providers:\n?", t)
    entry = f"  - provider: {block}\n    model: agnes-3.0-flash\n"
    if fm:
        i = fm.end()
        m2 = re.search(r"(?m)^\S", t[i:])
        j = i + m2.start() if m2 else len(t)
        newsec = t[fm.start():i] + "\n" if t[fm.start():i].rstrip().endswith(":[]") is False else t[fm.start():i]
        # 处理 fallback_providers: [] 空段: 展开成块
        if t[fm.start():j].strip() in ("fallback_providers: []", "fallback_providers:"):
            t = t[:fm.start()] + "fallback_providers:\n" + entry + t[j:]
        else:
            t = t[:j] + entry + t[j:]
    else:
        mm = re.search(r"(?m)^(?:toolsets:|agent:)", t)
        pos = mm.start() if mm else len(t)
        t = t[:pos] + "fallback_providers:\n" + entry + t[pos:]
    open(DEFAULT_CFG, "w", encoding="utf-8").write(t)
    # pyyaml 验活 (venv python 有 yaml)
    import glob
    for vp in glob.glob(os.path.join(HERMES, r"installs\*\environments\*\venv\Scripts\python.exe")):
        r = subprocess.run([vp, "-c",
                            f"import yaml;yaml.safe_load(open(r'{DEFAULT_CFG}',encoding='utf-8'));print('yaml-ok')"],
                           capture_output=True, text=True, timeout=30)
        if "yaml-ok" in r.stdout:
            return "added"
    # 没有可用的 venv python -> 退回 regex 自检
    if re.search(r"(?m)^ *- *provider:\s*" + re.escape(block) + r"\s*$", t):
        return "added(no-yaml-check)"
    return "FAIL"


def main():
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    results = {}
    reds, yels, grns = [], [], []

    # ---- 采集: 交易 5 席 + 其他 26 席 (从各 profile config + .env 实读)
    profiles = sorted(d for d in os.listdir(os.path.join(HERMES, "profiles"))
                      if os.path.isfile(os.path.join(HERMES, "profiles", d, "config.yaml")))
    trading = {"default", "chief", "risk-officer", "strategy-rd", "post-mortem"}
    seats = []  # (profile, role, provider_block, key_fp, endpoint)
    for prof in ["default"] + profiles:
        cfgf = DEFAULT_CFG if prof == "default" else os.path.join(HERMES, "profiles", prof, "config.yaml")
        if not os.path.exists(cfgf):
            continue
        t = open(cfgf, encoding="utf-8").read()
        mainp, fbs = main_provider_chain(t)
        chain = [mainp] + [f for f in fbs if str(f).startswith(("k10", "agnes-")) and f not in ("k10-1",) or True]
        for block in ([mainp] + list(fbs)) if mainp else list(fbs):
            if not block or block in ("k10-8", "k10-9") or block == "agnes-cn-pool":
                continue  # 池与孤儿另行处理
            bi = block_info(t, block)
            if not bi:
                continue
            base, ke, inline = bi
            key = inline or env_values(prof).get(ke, "")
            if not key:
                continue
            ep = CN if "127.0.0.1" not in base and ".cn" in base else (COM if ".com" in base else CN)
            if "127.0.0.1" in base:
                ep = "proxy"  # 池 proxy 块: key 是 dummy, 跳过探针
                continue
            seats.append((prof, block, fp(key), ep, key))
    # 去重 (同一 key 可能被多块引用)
    uniq = {}
    for s in seats:
        uniq.setdefault((s[3], s[4]), s)

    pool_keys = []
    try:
        pj = json.load(open(POOL_JSON, encoding="utf-8"))
        raw = pj.get("keys", pj) if isinstance(pj, dict) else pj  # 池 json 是 {endpoint, keys}
        pool_keys = [str(k.get("key") or k.get("api_key") if isinstance(k, dict) else k) for k in raw]
    except Exception:
        pass

    # ---- 探针
    def probe_one(fpkey, key, ep):
        base = CN if ep == CN else COM
        st = probe(base, key)
        results[f"{fpkey}@{ep[:20]}"] = st
        return st

    reds_seats = []
    for (ep, key), s in uniq.items():
        prof, block, fpk, _, _ = s
        st = probe_one(fpk, key, ep)
        if st != "LIVE":
            (reds_seats if prof in trading else yels).append(f"{prof}({block})={fpk}:{st}")
    # 池 keys (.cn)
    pool_wall = []
    for k in pool_keys:
        st = probe_one(fp(k), k, CN)
        if st != "LIVE":
            pool_wall.append(f"{fp(k)}:{st}")
    # 孤儿 k10-8/k10-9 (.com, default config inline)
    orphan = {}
    tdef = open(DEFAULT_CFG, encoding="utf-8").read()
    for blk in ("k10-8", "k10-9"):
        bi = block_info(tdef, blk)
        if bi and bi[2]:
            st = probe_one(fp(bi[2]), bi[2], COM)
            orphan[blk] = st
            if st == "LIVE":
                fbs = main_provider_chain(tdef)[1]
                if blk not in fbs:
                    r = add_to_default_fallback(blk)
                    if r in ("added", "added(no-yaml-check)"):
                        grns.append(f"{blk} 429 恢复 -> 已挂 default 备链({r})")
                    else:
                        grns.append(f"{blk} 429 恢复 -> 挂备链失败 {r}")
                else:
                    grns.append(f"{blk} LIVE 且已在备链")

    # ---- 留痕
    summary = {"ts": now, "seats": len(uniq), "pool": len(pool_keys),
               "red": reds_seats, "yel": yels, "grn": grns, "pool_nonlive": pool_wall,
               "orphan": orphan, "detail": results}
    os.makedirs(os.path.dirname(LAST), exist_ok=True)
    json.dump(summary, open(LAST, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    try:
        led = json.load(open(LEDGER, encoding="utf-8"))
        led["tasks"].append({
            "id": "t_agnes_key_sentinel_" + now[:10].replace("-", "") + "_" + now[11:16],
            "state": "DONE", "ts": now,
            "title": f"11-14 Agnes key 哨: 专属 {len(uniq)} 把 / 池 {len(pool_keys)} 把; RED {len(reds_seats)} YEL {len(yels)} GRN {len(grns)}; 池非活 {len(pool_wall)}; 孤儿 {orphan}",
        })
        led["ts"] = now
        json.dump(led, open(LEDGER, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    except Exception:
        pass

    # ---- 报障 (stdout: 全绿静默)
    out = []
    if reds_seats:
        out.append("RED Agnes key 哨: 交易席堵墙/死亡: " + " | ".join(reds_seats))
    if yels:
        out.append("YEL Agnes key 哨: 非交易席堵墙 %d 把: " % len(yels) + " | ".join(yels[:8]))
    if grns:
        out.append("GRN Agnes key 哨: " + " | ".join(grns))
    if pool_wall:
        out.append("INFO Agnes 池: %d 把非活(池内冷却自动规避): " % len(pool_wall) + " | ".join(pool_wall[:6]))
    print("\n".join(out))


if __name__ == "__main__":
    main()
