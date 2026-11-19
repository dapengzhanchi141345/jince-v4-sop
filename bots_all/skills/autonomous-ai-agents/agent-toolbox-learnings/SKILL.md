---
name: agent-toolbox-learnings
description: "核验并安装公众号推荐的第三方 agent 工具；已收录 Ekko Studio、agency-agents。"
version: 0.1.0
author: li-yanming, Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [agents, multi-agent, tooling, vetting, workbuddy]
---

# Agent 工具箱学习（第三方 AI agent 工具核验 + 安装）

用户（李彦明）关注的「小登登」类公众号常发「一句话部署 N 个 AI 员工」类工具测评，结尾都是「对 Hermes 直接说帮我装 X」。本技能存**已核验的工具条目 + 一套防吹的核验流程**，避免被情绪词带跑、盲装第三方脚本。

## When to Use
- 用户丢来一篇 AI 工具测评（公众号/知乎/小红书），要「学习」或「装一下」。
- 安装/跑第三方 agent 工具前，要先确认它真实、不碰现有 Hermes、落在哪。

Don't use：装 Hermes 官方自带插件/技能（那些不走第三方核验）。

## 核验流程（给任何「公众号推荐的工具」过一遍再装）
1. **验仓库真实性**：`curl -s https://api.github.com/repos/<owner>/<repo>` 读 `stargazers_count`/`forks_count`/`pushed_at`/`archived` —— star 数文章吹的多少，以 API 实读为准；`pushed_at` 看是否活跃；archived=true 别装。
2. **验安装方式**：读 README 的真实命令（`npm` / `pip` / `git clone + install.sh` / 桌面 App）。**先 dry-run**：agency-agents 用 `./scripts/install.sh --tool <x> --dry-run`；npm 先 `npm view <pkg> maintainers homepage version` 看谁发布。
3. **验落点 + 是否碰现有 Hermes**：安装前 `npm config get prefix`、看目标目录结构；安装后立刻 diff「我这套 Hermes 的运行时目录」有没有被改。第三方包落 `node_modules`/独立目录 ≠ 碰我（`C:\Users\ASUS\AppData\Local\hermes\hermes-agent\venv`）。
4. **验声称的功能范围**：只信「能实际跑起来」的能力；「调 7 个 agent」前提是那几个 agent 真装在本机——先 `which claude codex opencode grok`。
- **吹的成分标注**：区分「已核实事实」vs「文章说法」，回复里明写哪条没独立验到。
- **本机驱动层缺口**：这类工具的驱动层常是 Codex/Claude Code CLI——本机均未装；路由包（如 reverse-skill）不支持 Hermes 时，等价物 = Hermes 自己的知识库+技能沉淀（如 `mt4-ea-replication` 的逆向流水线）。

## 已收录工具（已核验）

### ① Ekko Studio（前身 Hermes Studio / Hermes Web UI）
- **仓库**：`EKKOLearnAI/hermes-studio`（GitHub 真）｜npm 包 **`hermes-web-ui` v0.7.23**｜官网 ekko-studio.xyz｜创建 2026-04，活跃。
- **是什么**：本地优先的多 agent 工作台 = 桌面 App + 本地运行时 + Web 控制台。把 **Hermes / Claude Code / Codex / OpenCode / Grok / Pi / DeepSeek Harness 7 套 agent 塞进一个面板**，群聊 `@agent` 路由、可视化工作流、文件浏览、模型/profile 管理、手机连。
- **安装**：`npm install -g hermes-web-ui && hermes-web-ui start`；也支持 Docker。维护者 bigjayz1990。
- **要点**：
  - 它跟「我这套 Hermes Agent」**不是一套**——它借用同名 "Hermes" 把 Hermes 当七把刀之一。装它 = 装独立 npm 包 + 起本地 Web 服务，不动我这套 Python 运行时。
  - 本机 node v22 / npm 10.9 已备，全局前缀 `E:\workbuddy\国外模型\hermes\node`（当前未装 hermes-web-ui）。
  - 「调 7 个 agent」需那几个 CLI 真装；本机 claude/codex/opencode/grok 均未在 PATH。

### ② agency-agents（虚拟 AI 公司 / 角色库）
- **仓库**：`msitarzewski/agency-agents`（GitHub 真）｜**实读 153,766 star / 24,807 fork**，2026-09-20 活跃，MIT。15 万 star 属实。
- **是什么**：200+「岗位 agent」定义文件，按部门分（engineering/design/marketing/sales/product/pm/testing/security/gis/game-dev/finance/research/healthcare/spatial-computing/specialized/paid-media/support…），每个带人格 + 工作流 + 验收标准。装进现有工具，**不新增运行时**。
- **安装**：`git clone` 后 `./scripts/install.sh --tool hermes`（也支持 claude-code/cursor/codex/gemini-cli/opencode/kimi 等 13 种）；或原生桌面 App（`brew install --cask msitarzewski/agency-agents/agency-agents`）。按部门装：`--division engineering,security`；按 agent 装：`--agent frontend-developer,ui-designer`。
- **坑（README 一致）**：① 别全选（token 烧在「出方案→评审→打回→再出」循环）；② OpenCode 运行时只注册 ~119 个，超出被静默丢（上游 bug）；③ `strategy/` 是策略剧本不是第 17 部门，装不了；④ 定义全英文。建议：先只装 1 个部门，给每个 agent 配模型（理解型喂强的、格式化杂活喂轻的），工作流对齐项目真实边界。
- **「207 个 agent」为文章/README 说法，本部门网络未独立验到确切数；部门数已验到。**

### ③ grokbot / grok-trading-desk（Grok LLM 交易架构核验，2026-11-02，0 安装）
- **来源**：用户看视频"grokbot 操作很给力"要求深度学习。GitHub API 实读：`joipdev/GrokBot`（TS，2 star，pushed 2026-09-01）、`zostaff/grok-trading-desk`（Python，17 star，pushed 2026-08-30）、`cryptozak27/grokbot`（EVM 派生版，0 star，pushed 2026-08-30）——**全是小个人仓，非热门产品；可吸收的是架构思想不是系统**，防吹标注：视频里"给力"≠仓库体量。
- **三仓共同架构（实读 README/源码描述核验）**：① LLM 只出**结构化快照**（JSON：direction/conviction/horizon/rationale，temp=0），不看余额、不选手数；② **风险层独立于模型、挡在模型与下单之间**（max position / daily loss cap / cooldown / kill switch，仓位是确定性代码）；③ **悲观回退"a model that fails is a model that says no"**：LLM/解析/管道任何失败 → 默认拒单/hold/reject，绝不默认"是"。
- **两条 SOTA 细节（外部参考，0 照搬）**：(a) 仓位三上限取最紧 = 该市场预算 15% / 当日剩余亏额 25% / 可用资金，再 × 信心 0.5~1.0（我方 G8 0.5% 倒算 + dd_brake 缩放同思路，不重造）；(b) 跨市场统一风控计数器：币的亏损吃同一日亏额度（我方 risk_state.json 已是账户级，对齐）。
- **金策落点**：L5 领 rd_queue `grokbot_llm_advisory_replay_20261102`（LLM 结构快照前向攒样，0 喂闸源，未过五验 = OBSERVATION）；L4 领 1 行闸审 = 逐条核对我方失败模式默认动作，任何"失败→默认下单"是红旗。本机唯一可 grep 的 rd_queue 在 `E:\workbuddy\金策宗师团\_github_mirror\jince-ledger\引擎决策\rd_queue.json`（grep `grokbot_llm_advisory` 验）。

## 1:1 复刻三件套（REA + reverse-skill + PentAGI）
- **来源**：X @ResearchWang《Codex 软件开发完整工作流》（2026-09）；2026-10-19 核验，全部 API 实读：
  - **REA**（morluto/rea，324,748 star，TS，MIT，极活跃）：MCP 逆向工具合集——二进制(Ghidra/IDA)/JS/Electron/.NET/网页/APK，结论带证据链。本机 `npx rea-agents setup` 直用；agent 技能 `npx skills add morluto/rea --skill reverse-engineer-anything`。
  - **reverse-skill**（zhaoxuya520/reverse-skill，42,583 star，MIT）：技能路由包（自动路由/按需装工具/进化经验库），支持 Claude Code/Cursor/Cline/Kiro，**不支持 Hermes**。
  - **PentAGI**（vxcontrol/pentagi，31,162 star，Go，MIT）：AI 红队多 agent 渗透测试，Docker 沙箱 + LLM key + Postgres/pgvector；Web UI :8443 默认 admin@pentagi.com/admin。
- **流水线四步**：REA 拆（证据链）→ reverse-skill 调度装环境 → 编程 agent **重写不抄源码** → PentAGI 扫自己的成品。
- **坑**：单点爆破最小功能别整套 SaaS；内存 <4G 别跑 PentAGI Docker；只扫自己的靶机。
- **决定：暂不装**。驱动层 Codex/Claude Code 本机缺失；哪天要复刻喊 Hermes：`npx rea-agents` 拆解 + Hermes 重写 + 需时再搭 PentAGI（先验 Docker）。落点：知识库 `ai-工具测评/1to1复刻三件套-REA-ReverseSkill-PentAGI核验.md`。

## 两者怎么选（给用户的取舍）
- 要**统一管理多个 agent 运行时**（后厨管理系统）→ Ekko Studio。
- 要**给现有 agent 批量加专职专家角色**（招一批厨师）→ agency-agents。
- 不冲突可叠：先 agency-agents 灌专家人格，再 Ekko Studio 把它们并排调度。

## Verification
- 回复里每条「事实」标注已核实 vs 文章说法。
- 装完任一工具：第三方目录 diff 通过（我这套 Hermes venv 未被改）；目标工具能实际 `start`/`list`。
- 装完 agency-agents：`./scripts/install.sh --tool hermes --dry-run` 先跑通再真装；确认落点是 `.hermes/skills` 而非覆盖现有技能。
