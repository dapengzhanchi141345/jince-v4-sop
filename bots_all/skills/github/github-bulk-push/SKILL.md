---
name: github-bulk-push
description: Use when pushing local trees to GitHub via Git Data API.
---

# GitHub 批量推送 via Git Data API（git push 被墙 / 无 gh CLI 时）

## When to Use
- git 协议推 github.com 失败（GFW 连接重置）、无 gh CLI，但有 PAT 且 api.github.com 可达
- 目录→私有仓的批量备份/镜像推送（数百~数万文件），需断点续传与逐仓对账
- 修复上一次坏推（树缺层/文件丢失）时的重锚流程
配套可运行代码片段（api 重试、blob 缓存、正确建树器、seed 轮询、对账）见 `references/git-data-api-recipe.md`。

## 前置（按序）
1. token 存 chmod-600 文件（scratch 目录，绝不进仓）；`GET /user` + `GET /rate_limit` 验证（core 限额 5000/小时，余量 <600 就规划续传）。
2. DNS 抖动：给 api.github.com 做 IP pinning（socket.getaddrinfo hook）或 DoH 回退；网络层异常重试+退避，HTTP 状态码不重试（400 偶发 malformed 除外，见下）。
3. **单写者**：重启队列前先杀掉旧推送进程并确认它真死了——日志时间戳会骗人，两个并发写共享 cache/日志会造成归属混乱。
4. 源树先本地过滤 junk（.venv、node_modules、__pycache__、logs、*.db、NUL/CON/PRN 等 Windows 设备名——设备路径会让 os.path 过滤器崩）。
5. 用户要「备份」时，本地 zip 镜像与远端推送并行做（存 内容中心\\备份\\，按日期命名），远端故障时兜底。

## 流程
1. **新仓 seed**：首提交走 Contents API `PUT contents/README.md`。新建仓有 provisioning 空窗：写操作 404 持续 30~90+ 分钟。每 45-60s 轮询、单 job 45 分钟上限；期间手动探测一次 seed PUT 可提前解锁。**绝不删仓重建**。
2. **blobs**：逐文件 `POST /git/blobs`（base64）。内容缓存键 = (repo, git blob SHA1)，JSON 原子保存（每 30 个上传存一次）——被杀后重跑免重传。blob 400（"malformed request... try resubmitting"）与 5xx（502 "Server Error" 等偶发服务端故障）都重试 ≤5 次、间隔 10s；其它码 raise。
3. **并集策略（备份不覆盖）**：`GET /git/trees/<base>?recursive=1` 取 {path: blob_sha1}，本地路径覆盖远端、远端独有保留。修复坏推时 base 取坏提交的 parents[0]，新提交 parent=base 并 `force=true` 更新 ref（**force 仅限自我修复重锚，共享/定时同步路径禁用**）。
4. **建树**：自底向上按目录 POST。中间目录必须登记进父树——**off-by-one 会静默丢整支子目录树且推送报成功**（见下 pitfalls 与 recipe）。
5. **扁根 422**：单次树 POST ~1000+ 条目会 422 "input too large"。远端是扁平根级（上千文件全在根目录）时不要并集，改推本地树（旧快照留在 git 历史，可查父提交恢复）。
6. **commit + ref**：`POST /git/commits`（tree + parents=[main head]，无 main 则 []），`POST /git/refs/heads/main {"sha":...}`。
7. **每仓推送后必须对账**：`GET /git/trees/main?recursive=1` 数 blob，与本地期望（本地文件 + 保留的远端独有 + README seed）比对；数量不符 = 坏推，禁止记账完成。对账全绿才把仓写入完成台账（JSON），重跑自动跳过。

## Pitfalls（规则 + 原因）
- **以远端 blob 计数验收，不以「已推 commit」日志验收**——坏树照样产生 201 成功提交（实测 747/1623、789/2254 两次坏推都是这样逃过自检的）。
- 建树中间目录登记用 `for i in range(1, len(parts))`（对 a/b/c.py 登记 a→根、a/b→a）；写成 `len(parts)-1` 会漏掉最深一级中间目录，父树不引用子目录 → 整支子树丢失，且树 POST 全部 201 无报错。
- 树 POST 条目数控制在 ~500 以内（~1050 观测 422，~150 正常）；超大目录改用多 commit 分批（每次 父树 + k 个新条目），不改路径。
- 新建仓 provisioning 空窗 30~90+ 分钟：轮询 seed、不删重建；跨 job 重启也不删。空窗可超过两个 45 分钟单 job 轮次，逐轮续跑不放弃队列。手动探测 seed PUT 成功后必须杀掉正在轮询的旧进程并重启队列——README 已存在时旧循环的 no-sha PUT 会 409 使任务失败，旧进程感知不到解锁（实测：probe 成功后旧 job 仍空转 45 分钟超时退出）。
- 限流 5000/小时：remaining 耗尽就睡到 X-RateLimit-Reset；blob 缓存让续传零成本，严禁硬撞。
- 同一批仓禁止两个推送进程并发（共享 cache JSON + 共享日志 = 竞争与归属混乱）。
- 30 分钟工具超时杀掉后台 job 属正常：凭 blob 缓存 + 完成台账立刻重启同队列即可，已传内容不重传。
