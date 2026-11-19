# -*- coding: utf-8 -*-
"""12 学科独立站部署到各自 GitHub Pages 仓 (gh api 直连, 绕 443 墙, 确定性 0 LLM).
[2026-10-08] 根治: 旧 sites_deploy_ghpages.py 推单体仓 li-yanming-sites(12 html 塞一个仓),
但 12 独立站实际各自活在 li-yanming-<slug> 仓 -> 升级脚本改完本地源后从没推上独立仓,
公网永远是旧的. 本脚本逐仓全量替换: 读本地 E:/workbuddy/内容中心/网站/sites/<slug>.html
-> 推各自 li-yanming-<slug> 仓 main 分支 index.html (Pages 入口).
用法: python sites_deploy_12indep.py
      02:00 cron 接线: 先 sites_daily_upgrade.py(升级本地源) 再本脚本(推 12 仓), 串行.
失败发声不静默: 任一仓 blob/tree/commit/ref 失败 -> 打印 [失败] 且 exit 1(让 cron 异常可见).
"""
import subprocess, os, base64, json, sys, time, datetime

SITE_OWNER = "dapengzhanchi141345"
SLUGS = ["math","chinese","english","physics","chem","bio","geo","history",
         "morality","it","music","pe"]
SITES_DIR = r"E:\workbuddy\内容中心\网站\sites"

def gh_get(api):
    r = subprocess.run(["gh","api","-H","User-Agent: sites-deploy-12",api],
                       capture_output=True, text=True, timeout=180, creationflags=0x08000000)
    return r.returncode, r.stdout, r.stderr

def gh_post(api, payload):
    r = subprocess.run(["gh","api","-H","User-Agent: sites-deploy-12","-X","POST","--input","-",api],
                       input=json.dumps(payload), capture_output=True, text=True, timeout=180, creationflags=0x08000000)
    return r.returncode, r.stdout, r.stderr

def _retry(fn, tries=6, backoff=2, what="gh-api"):
    """gh api 间歇截断('unexpected end of JSON input')退避重试护栏(与 jince_tick_push 同源根治)."""
    last = None
    for i in range(tries):
        last = fn()
        if last[0] == 0:
            return last
        if i < tries - 1:
            time.sleep(backoff * (i + 1))
    return last

def deploy_one(slug):
    local = os.path.join(SITES_DIR, slug + ".html")
    if not os.path.exists(local):
        print(f"[失败] {slug}: 本地源 {local} 不存在")
        return False
    b64 = base64.b64encode(open(local,"rb").read()).decode()
    repo = f"{SITE_OWNER}/li-yanming-{slug}"
    # ① 仓存在性(不存在->建; 已存在放行)
    rc,out,err = gh_get(f"repos/{repo}")
    if rc != 0:
        print(f"[建仓] {repo}")
        rc2,out2,err2 = gh_post("user/repos", {"name":f"li-yanming-{slug}","private":False,"visibility":"public"})
        if rc2 != 0:
            print(f"[失败] {slug} 建仓: {err2.strip()[:200]}")
            return False
    # ② 取 main HEAD(空仓->base=HEAD, parents=[])
    rc,out,err = gh_get(f"repos/{repo}/git/ref/heads/main")
    base = json.loads(out)["object"]["sha"] if rc==0 else "HEAD"
    # ③ blob(重试护栏)
    def do_blob():
        return gh_post(f"repos/{repo}/git/blobs",
                       {"content": b64, "encoding":"base64"})
    rc,out,err = _retry(do_blob)
    if rc != 0:
        print(f"[失败] {slug} blob: {err.strip()[:200]}")
        return False
    blob_sha = json.loads(out)["sha"]
    # ④ tree(其它 entry 保留 + 替换 index.html)
    if base != "HEAD":
        rc_t, out_t, err_t = gh_get(f"repos/{repo}/git/trees/{base}")
        remote_tree = json.loads(out_t) if rc_t == 0 else {}
    else:
        remote_tree = {}
    entries = [e for e in remote_tree.get("tree", []) if e.get("path") != "index.html"]
    entries.append({"path": "index.html", "mode": "100644", "type": "blob", "sha": blob_sha})
    rc,out,err = _retry(lambda: gh_post(f"repos/{repo}/git/trees", {"tree": entries}))
    if rc != 0:
        print(f"[失败] {slug} tree: {err.strip()[:200]}")
        return False
    tree_sha = json.loads(out)["sha"]
    # ⑤ commit + 推 main(force 全量替换, 空仓首推 parents=[])
    parents = [base] if base!="HEAD" else []
    rc,out,err = _retry(lambda: gh_post(f"repos/{repo}/git/commits",
        {"message":f"{slug} 12独立站升级 {datetime.datetime.now():%Y-%m-%d}",
         "tree":tree_sha,"parents":parents}))
    if rc != 0:
        print(f"[失败] {slug} commit: {err.strip()[:200]}")
        return False
    csha = json.loads(out)["sha"]
    rc,out,err = _retry(lambda: gh_post(f"repos/{repo}/git/refs/heads/main",
        {"sha": csha, "force": True}))
    if rc != 0:
        print(f"[失败] {slug} 推main: {err.strip()[:200]}")
        return False
    print(f"[成功] {slug} 已推 {repo} (公网 https://{SITE_OWNER}.github.io/li-yanming-{slug}/)")
    return True

def main():
    ok, bad = [], []
    for s in SLUGS:
        (ok if deploy_one(s) else bad).append(s)
        time.sleep(0.5)  # 限流温柔
    print(f"[部署] 12独立站: 成功 {len(ok)}/12 {ok}")
    if bad:
        print(f"[失败] 未推上: {bad}")
        sys.exit(1)
    sys.exit(0)

if __name__ == "__main__":
    main()
