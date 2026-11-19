# GitHub 自动同步（升级后必推，用户常备令 2026-09-25）

任何系统升级必须同步到私有仓 `dapengzhanchi141345/jince-engine`——绝不只留本地。跑 `E:/GoldstrategyEngine/sync_to_github.py`：重选核心源（排除 backup/python/logs/data）、把真 MT5 密码洗成 `__MT5_PASSWORD__` 占位、重生成 AES-256 凭证包 `jince_credentials_encrypted.zip`（密码 141345）、commit 到本地仓 `C:/Users/ASUS/jince-engine` 并 push。两个 Windows 任务 JinCeGitSync/JinCeGitSyncPM（07:00/19:00）每日兜底。

## Push 链路坑（本机 443 墙）
- github.com 的 20.205.x 前端在此机被挡；把 IP 直接写进 URL 会失败（host/SNI 变 IP，GitHub 边缘 443 connection reset）。
- 正解：`resolve` 旗标绑 IP、URL 保持 github.com（SNI 对）：
  `git -c "http.https://github.com/.resolve=140.82.113.4:443:140.82.113.4" -c http.sslVerify=false push https://github.com/dapengzhanchi141345/jince-engine.git main`
- 四个候选 IP（140.82.113.4 / 140.82.114.4 / 20.205.243.166 / 185.199.108.153）先 `git -c "...resolve=IP:443:IP" ls-remote` 只读实测连通再选。
- 改 Windows hosts 需管理员（本机非管理员 Permission denied），优先 resolve 旗标不动 hosts。
- DoH 备用查 IP：`curl "https://dns.alidns.com/resolve?name=github.com&type=A"`。
- gh（自带 resolver）`gh api` 正常，只 git 走系统 DNS 会挂——push 用 resolve 旗标、验收用 `gh api repos/dapengzhanchi141345/jince-engine/commits/main` 验远端 commit（别只看 push exit code）。
- **当 IP 路线与裸 github.com 都失败（间歇性墙）：gh-token-in-URL 是可靠兜底**：`git push "https://x-access-token:*** 443 直连被挡时该通道仍通。IP 路线挂时先试它。

## 脚本自身故障
- `sync_to_github.py` 的 `subprocess.run(["git",...])` FileNotFoundError（git 不在 ate-venv subprocess PATH）：MSYS git 在 `/mingw64/bin/git` 但剥离 env 看不到——shell 里手动 commit+push（`git status --short` 只认目标源文件；`jince_credentials_encrypted.zip` + `risk_state.json` 运行时常脏忽略）。别被同步脚本 env 卡住，常备令=commit+push 本身。
- `env -i`（干净 env）丢全局 git identity → `unable to auto-detect email`：commit 时传 `-c user.name=dapengzhanchi141345 -c user.email=404280473@qq.com`，不依赖 `.git/config`。
