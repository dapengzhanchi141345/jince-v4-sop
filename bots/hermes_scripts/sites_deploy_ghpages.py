# -*- coding: utf-8 -*-
"""12 学科站部署到 GitHub Pages (gh api 直连, 绕 443 墙, 复用金策看板根治路).
确定性 0 LLM, 失败发声不静默. 本地 sites_deploy/ -> Pages 仓 main 分支全量替换.
"""
import subprocess, os, json, datetime, base64, sys

GHPAGES_REPO = "dapengzhanchi141345/li-yanming-sites"
LOCAL = os.path.dirname(os.path.abspath(__file__)) + "\\sites_deploy"
FILES = ["index.html","math.html","chinese.html","english.html","physics.html",
         "chem.html","bio.html","geo.html","history.html","morality.html","it.html","music.html","pe.html"]

def gh_get(api):
    r = subprocess.run(["gh","api","-H","User-Agent: sites-deploy",api], capture_output=True, text=True, timeout=120, creationflags=0x08000000)
    return r.returncode, r.stdout, r.stderr

def gh_post(api, payload):
    r = subprocess.run(["gh","api","-H","User-Agent: sites-deploy","-X","POST","--input","-", api],
                       input=json.dumps(payload), capture_output=True, text=True, timeout=120, creationflags=0x08000000)
    return r.returncode, r.stdout, r.stderr

def main():
    local = LOCAL
    # 0. 验仓存在(不存在则建 Pages 仓)
    rc,out,err = gh_get("repos/%s"%GHPAGES_REPO)
    if rc!=0:
        print("[建仓] %s 不存在, 创建..."%GHPAGES_REPO)
        rc,out,err = gh_post("user/repos", {"name":"li-yanming-sites","private":False})
        if rc!=0:
            print("[失败] 建仓: %s"%err.strip()[:200]); sys.exit(1)
    # 1. 取 main HEAD(可能无 -> 空仓 base=HEAD, commit parents=[])
    rc,out,err = gh_get("repos/%s/git/ref/heads/main"%GHPAGES_REPO)
    base = json.loads(out)["object"]["sha"] if rc==0 else "HEAD"
    # 2. 逐文件传 blob(gh api 直连, 绕 github.com 443 墙)
    entries=[]
    for f in FILES:
        p = os.path.join(local, f)
        if not os.path.exists(p):
            print("[跳过] %s 不在本地"%f); continue
        b = open(p,"rb").read()
        rc,out,err = gh_post("repos/%s/git/blobs"%GHPAGES_REPO,
                             {"content":base64.b64encode(b).decode(),"encoding":"base64"})
        if rc!=0:
            print("[失败] blob %s: %s"%(f,err.strip()[:200])); sys.exit(1)
        entries.append({"path":f,"mode":"100644","type":"blob","sha":json.loads(out)["sha"]})
    # 3. 建 tree
    rc,out,err = gh_post("repos/%s/git/trees"%GHPAGES_REPO, {"tree":entries})
    if rc!=0:
        print("[失败] tree: %s"%err.strip()[:200]); sys.exit(1)
    tree_sha = json.loads(out)["sha"]
    # 4. 建 commit(parents=[base] 若 base 非 HEAD)
    parents = [base] if base!="HEAD" else []
    rc,out,err = gh_post("repos/%s/git/commits"%GHPAGES_REPO,
                          {"message":"daily 12学科站升级 %s"%datetime.datetime.now().strftime("%Y-%m-%d"),
                           "tree":tree_sha,"parents":parents})
    if rc!=0:
        print("[失败] commit: %s"%err.strip()[:200]); sys.exit(1)
    csha = json.loads(out)["sha"]
    # 5. 推 main(force 全量, 空仓首推 OK)
    rc,out,err = gh_post("repos/%s/git/refs/heads/main"%GHPAGES_REPO, {"force":True,"sha":csha})
    if rc!=0:
        print("[失败] 推 main: %s"%err.strip()[:200]); sys.exit(1)
    print("[成功] 12 学科站已推 GitHub Pages (gh-api 全量推, 公网 https://%s.github.io/%s/)"%(
        GHPAGES_REPO.split("/")[0], GHPAGES_REPO.split("/")[1]))
    sys.exit(0)

main()
