---
name: content-center-discipline-sites
description: "各学科 12 站 HTML 网站工程。Use when 提到学科网站/网站升级/进度通报/12站台账/二期学科。"
---

# 内容中心·各学科网站工程 (李老师下令, 2026-10-05 建, 永远不停)

## 单一事实源
- 站点: `E:\workbuddy\内容中心\网站\sites\<slug>.html` (12 站, slug: math/chinese/english/physics/chem/bio/geo/history/morality/it/music/pe; 二期: 考研/中医/财会/玄学/博弈等按同制度扩)
- 制度: `E:\workbuddy\内容中心\网站\00_工作制度.md` (验收线/派工/监控规则都写在这)
- 台账: `网站\进度台账\网站进度台账.md` (人读) + `网站\进度台账\升级状态.json` (机读, 每站 count/last)
- 升级日志: `网站\升级日志\升级日志_YYYY-MM-DD.md`; 通报: `网站\每日通报\`
- 脚本: 升级 `sites_upgrade_and_deploy.py` / 汇报 `sites_daily_report_0845.py` / 通报 `sites_daily_report.py`, 都 no_agent 0 LLM
- cron job: 详见「排期」节 (02:00 升级+部署唯一一班, 05:00 汇报, 22:30 通报, 全在夜窗), 在 `E:/workbuddy/国外模型/hermes/cron/jobs.json`

## 验收线 (李老师铁律, 建/改任何一站都要满足)
1. **单文件 HTML, file:// 双击独立可用** — 零外链零 CDN (grep `https?://|cdn.|unpkg|jsdelivr` 必须 0), 功能原生 JS; 不能把当前电脑当服务器 (微机室局域网分发铁律)。
2. 页脚必须带水印 `李彦明 15684394135`。
3. 全学段知识体系 + ≥3 个真能用交互功能。
4. 验货四连: `ls` 文件在 + 大小 + `grep -c 15684394135` 水印=1 + 离线自检 0 外链。

## 排期 (李彦明铁律: 网站长期任务全部收进 22:00–05:00 夜窗, 白天零负载, 不说改就一直持续; 2026-10-09 补令: 升级+部署一天只跑一班)
- **02:00** 升级+部署 (job `c2e571497bca`, 脚本 `sites_upgrade_and_deploy.py`, 增量升级 + gh-api 推 12 独立仓 Pages) — **唯一一班升级+部署**
- **04:00 升级+部署已停 (job `0c76706b8735` paused, 2026-10-09)**: 原为夜窗第二班, 与 02:00 重复, 李彦明令"一天跑太多次减为一班"后停掉
- **05:00** 独立站汇报 (job `b8766acc0f58`, 脚本 `sites_daily_report_0845.py`, 逐站验公网 200 + 掉队名单 + 大白话投群)
- **22:30** 每日通报 (job `websiter2230rp`, 脚本 `sites_daily_report.py`, 各站今日升级/掉队点名)
- **已废**: 旧 07:30 升级 job `websiter730up` 已暂停, 旧 08:45 汇报已挪 05:00
- 工作制度里"掉队站次日 07:30 优先补"已改"次日 02:00 优先补"
- 升级机制: `sites_daily_upgrade.py` 从池文件 `增量池/<slug>.jsonl` (14条/站, 2026-10-09 建) 按日期取模追加 1 条增量到该站 footer 前, 真改文件才计数(防刷数), 饱和站报[全用完]往池文件加行

## 每日升级机制 (永不停)
- **02:00 唯一一班** 升级+部署 (`sites_upgrade_and_deploy.py`, 脚本双份存: `内容中心\网站\脚本\` + `hermes\scripts\`(cron 读后者), 改完必双份同步): 每站增量升级 + gh-api 推 12 独立仓 Pages, 升级日志 + 升级状态.json 留痕。
- 05:00 `sites_daily_report_0845.py`: 读独立站台账+升级状态.json, 逐站验公网 200 + 掉队名单 (连续 2 天未升级), 大白话投群 + 落 每日通报/。
- 22:30 `sites_daily_report.py`: 汇总 12 站 状态/累计升级/最后升级日/掉队名单, 投群 + 落 每日通报/。
- 收到 22:30 通报 / 05:00 汇报 cron 消息时: 看掉队名单([掉队] 已 N 天未升级), 别当部署/gh 故障——公网=活只说明 Pages 线上快照未受影响, 掉队 = 该站源内容累计升级数停滞; 先查该站升级状态.json 的 last 日期 + 当日 02:00 升级日志: 日志报"饱和" = 增量池断粮(往 增量池/<slug>.jsonl 追加行, 下一班自动接上, 不用手补跑), 非饱和才查当班 02:00 排期/gh 步;  有掉队 → 该站次日 02:00 优先补; 全绿 → 一句"正常"即可, 不展开。
- **12 站同时掉队 N 天（非个别站）= 增量池断粮的群体信号（11-11 实例：全 12 站卡 11-06，掉队 5 天）**：逐站查 `网站/增量池/<slug>.jsonl` 余量（`wc -l`）——每站每晚耗 1 条，池 14 条 ≈ 2 周饱和；余量 < 掉队天数即断粮坐实。治法 = 往 12 个池文件各追加 ≥ 饱和周期条数（每行保留 `%d` 日期占位、不重复站内已展示条目），下一班 02:00 自动接上。**责任 bot 点名用一条批量总线（cc 全部 12 owner）而非 12 条逐发**——逐发既烧额度又撞 429（见「认领单批量派 429」条），一条 cc 全组 + 抄 workbuddy 主通道即可；掉队是内容生成断供不是推送故障，汇报别归因 gh/443（同步成功 ≠ 升级发生：sync 推的是当前快照，池断粮时快照冻结，页脚"最后升级"自然不翻）。

## GitHub Pages 部署 (2026-10-07 起, 12 站接学科智能体 AI 面板)
- **AI 面板注入**: `网站/脚本/inject_agent_panels.py` 给 12 站 `</body>` 前注入"学科智能体问答"面板(预设按钮+输入框+fetch Agnes API), 幂等已含 agent-panel 跳过. 离线降级显示"在线 AI 暂不可用,看站内题库", 不破 file:// 单文件离线铁律.
- **入口页** `index.html` = 全学科 4 列卡片导航, footer 带 `李彦明 15684394135`.
- **独立站架构(2026-10-07 用户令"每个学科独立网站 不能合起来")**: 12 站拆成 **12 个独立 GitHub 仓** `dapengzhanchi141345/li-yanming-<slug>`(各站独立仓+独立 Pages 公网 URL, 互不混在同一页). 每站仓内只有 index.html(该站 html 当 index). 台账 `网站/进度台账/网站独立站台账.json`(12 站 owner_bot+url). 旧合并仓 li-yanming-sites(12 站挂一个仓)已被独立仓取代.
- **443 墙坑(今日多次复现)**: `git push`/`ls-remote` 直连 github.com:443 间歇被墙(Failed to connect port 443). 根治路 = **gh api 全量推**: 建仓(`gh api user/repos`)→逐文件 `gh api git/blobs`→`git/trees`→`git/commits`→`git/refs/heads/main`(force). api.github.com 不经 github.com 443 墙, 可靠.
- **空仓 409 坑(今日实撞)**: 新建空仓时 `git/blobs` API 直接 409 `Git Repository is empty` — blob/tree 要先有一个 commit 才能挂. **空仓首推必走 contents API**: `gh api -X PUT repos/{owner}/{repo}/contents/index.html --input - (json: message+content base64)` — 它原子建 file+commit+branch, 空仓也 OK, 完全绕开 blob 409. **后续更新**同路但需带 `sha` 字段(该文件当前 blob sha, 取自 `GET contents/{path}`), 缺 sha 报 422.
- **私仓不开 Pages 坑(今日实撞)**: 建仓 `gh api user/repos` 若限流恢复后参数没传对会建成 **private=true**, 私仓 Pages 不生成公网 URL(一直 404). 建完必 `GET repos/{...} --jq .private` 验, 是 true 就 `PATCH repos/{...} -f private=false` + 重 `POST /pages`.
- **批量建仓限流坑(今日实撞)**: 连发 12 仓 `gh api` POST 触发 `secondary rate limit`(403 临时封锁, 几十秒). 节奏 = 仓间 `sleep 3-8s`, 限流命中 `sleep 30-40s` 重试, 别一口气 12 连发.
- **gh api 截断响应坑("unexpected end of JSON input", 今晚 23:xx 实撞)**: 外网断档 + gh api 间歇抖叠加时, `git/blobs` 上传偶发返回截断 JSON(23:10/23:15 行情喂两拍即此). 判据: 先 `gh api rate_limit --jq .resources.core` 看余量 — 若 remaining 满(非账号级限流) + `gh auth status` token 正常 = 纯间歇抖, **fail-open 自动重试即消, 不连刷**(连刷加剧限流), 下一 cron 边界自愈; 若 core.remaining 见底才是账号级限流才需深查. 别把间歇抖误判成硬故障.
- **改被循环重算的 state 文件会被冲回(金策 risk_freeze_state.json 同族坑)**: 风控闸/全链每 30min 重算 state, 手工改 state 只活一轮就冲回。持久参数须落独立 policy 文件(如 `intraday_policy.json`)由重算脚本读取, 改源头而非改产物; 改完必重跑一次重算脚本 + 实读 state 验证真生效, 别只看自己写进去的字段.
- **部署脚本**: `网站/脚本/sites_deploy_ghpages.py`(gh-api 全量推单仓) + 独立站逐仓推走上面 contents API 套路. 排期与 job_id 一律看「排期」节 (02:00/04:00 升级+部署 / 05:00 汇报 / 22:30 通报).
- 各站 owner bot: it=码智君(it-edu), 余 11 站对应学科主团 bot 长期维护.

## 坑
- **网站脚本存了两套副本, cron 只读 hermes\scripts 那套(2026-10-09 实撞, 改错目录=白改)**: `sites_daily_upgrade.py`/`sites_upgrade_and_deploy.py`/`sites_deploy_12indep.py` 在 `E:\workbuddy\内容中心\网站\脚本\` 和 `E:\workbuddy\国外模型\hermes\scripts\` **各存一份**。
  - **cron 的 `script` 字段是相对路径, 默认解析在 `hermes\scripts`(不随 job 的 workdir 走)** → 02:00/04:00 两班升级+部署跑的是 `hermes\scripts` 那份; 只改 `内容中心\网站\脚本\` 那份**不生效**(10-09 实撞: 改了内容中心那套, cron 04:00 还是旧逻辑 0/12+老文案)。
  - **改完必双份同步**: 改 `内容中心` 那份后 `cp` 到 `hermes\scripts` 同文件名覆盖, 再 `md5sum` 两边对一致 + `python -m py_compile` 验语法 + 实跑 hermes\scripts 那份验逻辑。
  - 升级脚本的数据路径(SITES_DIR/STATE/LOG_DIR/增量池)都是**绝对路径**指回内容中心, 两套脚本读同一批站点/台账/池 → 不会各升各的。
- **增量池耗尽导致"升级永不停"空转(2026-10-09 实撞)**: 池只有内置 2 条+饱和 bug(只试 idx/idx+1 两条就报饱和) → 12 站次日全轮空, 02:00 cron 升级 0/12, 台账不翻。治: ①池改外部文件 `网站/增量池/<slug>.jsonl`(每站 14 条, 每行一条, 饱和周期 2 周) ②`_load_pool()` 池文件优先、内置 UPGRADES 兜底 ③upgrade_site 全池遍历找"没加过的条目"才追加, 全部加过才报饱和(报错文案提示往 jsonl 加行续量)。**池耗尽判据: 日志出现 `[饱和] xx 增量池已全用完(N条)` = 往 增量池/xx.jsonl 追加行即可, 不改脚本。**加行照格式: 每行 `【类别+%d】内容`, `%d` 是升级脚本替换的日期占位——追加行必须保留它, 丢了站点就缺日期; 类别(法条/案例/辨析/易错等)跟该站现有条目风格一致, 内容不重复池内已有条目、也不重复站点页面上已展示过的条目(加前先搜该站 html); 一次补够一个饱和周期(≥2 周条数, 每站每晚 1 条), 补完 `grep -c . 池文件` 验条数增加, 下一班 02:00 自动接上, 不必手动补跑**。
- **升级 0/12 ≠ cron 挂了**: 先实读 升级日志/ 当日日志 + `升级状态.json` 各站 last 日期——last 不翻且日志报"饱和/已加"= 池断粮(按上条续量), 不是调度问题。调度问题才查 cron jobs.json last_status。
- **暂停被替换的旧 job, 别删** (排期重排时): 把接管者建好(新 job)后, 旧 job 用 `cronjob_manage` 的 paused=true + paused_reason 留痕接管关系(哪条 cron 接管了它、何时), 不 remove。理由: 留痕可审计 + 一键 resume 回退; 删了就没有"谁接管了"的记录。
- **AI 面板模板语法进普通 HTML 会崩(码智君实报, 永久)**: `inject_agent_panels.py` 注入的面板里任何 `${...}`/`{{...}}`/`...}` 式模板占位(如 `key:""` 没填实)在普通 `<script>` 里被浏览器当 JS 解析, file:// 双击直接语法报错。铁律: 注入面板只用纯 JS 字面量(key 空串降级离线题库), 禁模板占位符; 在线 key 由主进程填实后再推 Pages, 各站保留无 key 自动降级开关。
- **认领单批量派给学科 bot 撞 429(额度墙, 常态)**: message_agent 派 12 张认领单时各 bot 的 LLM 调用吃当日文本额度, 额度见底后在途回执全 429(每 1min 放 1 次)。别连刷(加剧限流)——认领单已入队列不丢, 等次日额度重置自动回执; 确定性 0 LLM 活(升级/部署/验活)不受影响照跑。
- **子代理自称完成但没落文件**: 批量 delegate_task 建网站时, 子代理可能只跑 1-3 个 api_calls 就报 "开始写" 然后 failed/completed, 文件根本没写 (本会话 12 站里 5 站就是这么漏的)。规则: 每批子代理回收后**必 ls 验货**, 缺的站主进程直接自己写 (不重派), 写完四连验货; 429 死账 (免费池额度用完) 同此 — 活由主进程兜, 子代理池切付费池 (见 provider-pool-audit)。
- **升级脚本是确定性 0 LLM，免费池 429 不影响它** — 网站线不依赖 LLM 额度，这是它"永不停"的底气; 别把 LLM 活 (如人工选题) 塞进升级 cron。
- **部署脚本依赖 gh CLI + gh 认证，两者随用户 profile 丢失即全线断（区别于 443 墙）**: `sites_deploy_12indep.py` 走 `gh api` 全量推，在 `gh` 不在 PATH/没装、或 gh keyring 认证随旧 profile 没了时报 `FileNotFoundError: [WinError 2]` → 12 站 Pages 全线停更（线上快照冻结，脚本 exit=1）。cron 输出只有 wrapper 一行"exit=1"没细节——**手动跑一遍脚本抓真实 traceback 才能定位**。修：重装 gh + `gh auth login`（凭证在用户侧，不给 token 修不了）或改写 curl+token；`where gh` + 查 .env 的 token 键名（只看键、不打印值）先定"缺 CLI 还是缺认证"。 ② 金策看门狗 `extnet=down`（api.ipify.org 单端点探活）与该 face 同现 ≠ 外网断：`curl -s -m 3 https://api.github.com` 返回 200 + `gh auth status` = not logged in 时，唯一根因就是 gh 未鉴权（缺 token），卡 token 期间 02:00 部署 job 只等不暂停。整机工具链丢失（ATE/终端/gh 一起没）的分诊与恢复分工：载技能 mt5-multiagent-trading，读它的 disaster-triage 参考文件（skill_view name=mt5-multiagent-trading file_path 列 linked files 找 disaster-triage）。
- **改长期任务排期时: 别只挪 cron, 要连人读的 00_工作制度.md 一起改**。工作制度里硬编码了具体时刻(旧"次日 07:30 优先补"、"每日 07:30 升级"), 只改 jobs.json 的 cron 时刻不改制度文案, 制度文档会自相矛盾——下次照制度文档排工又会排回旧时刻。铁律: 改排期三处齐改 (cron jobs.json + 00_工作制度.md 文案 + 本技能排期节), 改完 grep 制度文档确认无残留旧时刻。
