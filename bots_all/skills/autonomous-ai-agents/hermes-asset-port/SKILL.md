---
name: hermes-asset-port
description: "Use when 打包 Hermes bot/专家资产给另一台 Hermes 学习或迁移。"
version: 0.1.0
author: li-yanming, Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [profiles, packaging, sanitize, port, expert-teams]
    related_skills: [agent-team-to-bot-fleet, mt5-multiagent-trading]
---

# 打包 Hermes 专家资产给另一台 Hermes 学习

用户说「把 XX bot 的数据打包，加上 YY，我要让另一个 Hermes 学习」时走本工序。产出 = 一个目录 + 同名 zip，按资产块分子目录，附 README 教对方接机。

## 范围界定（先查清再动手）
- 用 `search_files target=files pattern=*关键词*` 扫全 workbuddy 找资产根；用户点名的资产可能有散落的共享工作区（如金策宗师团在 `E:\workbuddy\金策宗师团\`，profile 在 `E:\workbuddy\国外模型\hermes\profiles\`）。
- 每块资产先 `ls` + `du -sh` 摸底体量，把「用户点名的内容线」与「同目录混排的其他内容」分开——成品目录常混多线稿件（如山海拾珍里考研英语 + 岐黄医典），按内容筛选而非整目录拷。
- **技能有两棵树、量级大且互相重叠**：default 在 `E:\workbuddy\国外模型\hermes\skills\`（~128 SKILL.md），每个专家 profile 又各有一份 `profiles/<名>/skills/`（28 个 profile 共 ~556 个，其中 ops-manager / chief / strategy-rd / risk-officer 四大 profile ≈40M，大量是 default 的重复拷贝）。任务若是「备份/打包全部技能」，别逐 profile 整拷（会膨胀 + 重复）——按内容哈希去重，或只传 default + 各 profile 的**新增自定义**技能。

## 每个 profile 拷什么（不是整目录）
profile 目录 30+ 项里只有这些有学习价值，其余全是不透明噪声：
- **拷**：`SOUL.md`、`profile.yaml`、`config.yaml`（脱敏后）、`memories/*.md`（不含 .lock）、自定义技能目录（`golden-strategy-*`、`calc-bazi`、`*-sota` 等——看 `skills/` 一级目录，bundled 类目目录如 apple/creative/github 不拷）、`cron/jobs.json`。
- **不拷**：`.env`（真密钥）、`state.db*`、`projects.db`、`sessions/`、`cache/`、`backups/`、`logs/`、`auth.lock`、`*.etag`、`audio_cache`、`image_cache`、`sandboxes/`、`pending/`、`runtime/`、bundled 技能类目、**`.git/`（资产根内任意目录里——部署镜像仓、`_push_history` 等：remote URL 常以 `https://x-access-token:<PAT>@github.com/...` 内嵌令牌凭证，拷工作区文本救不了，必须整目录排除；README 注明对方需自配自己的 remote 凭证）**。
- 共享技能单列一块（如 `devops/` 整个类目 + 根级数据 json），不复制进每个 profile。

## 脱敏与密钥安全
1. **指纹判定靠磁盘级扫描，不靠看到的文本**：config.yaml 的 api_key 有时磁盘上是指纹形式（`sk-xxx...yyyy`），有时是真完整 key；而终端/文件展示层会把真 key 脱敏显示成 `sk-前缀...后缀`，与指纹一模一样——**屏幕上看到的指纹形态不能证明磁盘上是指纹**。唯一判据是磁盘级校验正则 `sk-[A-Za-z0-9-]{20,}`：指纹的 `...` 会断开匹配，天然零命中；**一旦命中即磁盘上存在真 key，必须脱敏**（脱敏后该正则须归零）。
2. 脱敏：对每个 profile 的 config.yaml 一律置空**全部** api_key 行（值常为无引号形式，带引号的旧正则 `'.*?'` 会整段漏掉真 key——必须用通配版）：`re.sub(r"(?m)^(\s*api_key:\s*)\S.*$", "\\1''", txt)`（幂等，已置空/空行不受影响）。`.env` 直接不拷。
3. **外发前双向扫描**：
   - 真 key 拦截：`grep -rnE "sk-[A-Za-z0-9-]{20,}" <包>` 须零命中（指纹带 `...` 会自然排除）。
   - 反向核查：数包内 config.yaml 里 `^\s*api_key:` 行总数，要求**每一行都以 `''` 结尾**（两数相等才算全部置空；无引号真 key 置空后也是 `''`），别只正向扫就收工。
4. **排除运维脚本**：资产根下 `_` 前缀脚本（`_dist_keys.py`/`_keymap.py`/`_probe_keys.py` 这类 key 分发/探测工具）是内网运维件，不进外发包；README 注明哪些路径不在包内（如交易引擎 `E:\GoldstrategyEngine`）、对方需自行配 key。
5. **个人隐私匿名化，不只拦 key**：手机号、微信 iLink 账号/user_id、MT5 账户号等 PII 一律替成 `<PHONE>`/`<WEIXIN_ACCOUNT_ID>`/`<MT5_ACCOUNT>` 占位符。校验时逐类扫（手机号 11 位、账号域名、账户号），命中清零才算脱敏完成；sota 技能示例数据里也常有假/真手机号混入，别只扫 config。

## 技能筛选：用 .bundled_manifest 而不是硬编码类目名
- 各技能目录的 `.bundled_manifest` 是**官方技能名清单**（`名称:哈希` 逐行）。打包自定义技能时读该文件（没有就空集），只拷不在清单里的技能——硬编码一套类目名白名单会漏掉藏在官方类目（apple/creative/github）下的用户新增技能（如 devops/mt5-multiagent-trading）。根目录与各 profile 的清单可能不同，**取各自目录自己的**。

## 内容筛选坑
- **二进制文件不进 `grep -rl` 结果**：按关键词筛内容线的成品时，`grep -rl` 只报 md/html 文本命中，PNG 封面等二进制全漏。补救：按命名规律用 glob 补拷（`cp */*关键词*封面*.png`），再清掉混入的其他线文件。
- **共享多线日志不整拷**（如 12 站共用的升级日志/操作日志）：按行 `re.search(r"<线slug>|<线中文名>", ln, re.I)` 只抽目标线行，带 `## 来源: <文件名>` 头合并成单文件进包；README 注明「原始全量日志留源机，本包为提取件」。
- **路径抽象要覆盖双反斜杠（JSON 转义）与正斜杠**：`E:\\workbuddy`（jobs.json/.json 数据里的转义双反斜杠）与 `E:/workbuddy`（代码写成 / 的）都要替换，只处理单反斜杠会让 JSON 源里路径全漏。占位符替换顺序按 key 长度降序（长路径先）。
- **`__pycache__` 与二进制不进包**：`os.walk` 时 `dirs[:] = [x for x in dirs if not x.startswith(".") and x != "__pycache__"]`；非文本扩展名走 `shutil.copy2`。`.lock`/`.db`/`.etag`/`.pyc` 全排除——否则 py_compile 缓存会把本机路径打进二进制再被校验误报。
- 多行 Python 脚本走 `write_file` 落盘再跑，不走 heredoc（Windows 中文路径 + 嵌套引号断行坑）。

## 交付
- **技能全树推 GitHub（`E:/workbuddy/国外模型/hermes/scripts/skills_github_sync.py`）**：镜像 default 技能树 + 全 28 profile 技能树（~4467 文件）→ commit → `push_via_api`（gh api 绕 git 443 墙）推私有仓 `hermes-skills` main。**全量跑 ~1h（实测 3605s）：前台 terminal 420s 必超时——一律 background=True + notify=True 拉，看 log 尾 `commit <sha> 已推 …/hermes-skills (main), N 文件` 才算推成**；blob 走 sha256 去重缓存增量（log 报「本轮新传 N blob」，二跑远小于全量）；gh 鉴权走 keyring（`gh auth status` 先验，未鉴权才用 token env 注入，token 不落盘/日志）。git 推送 443 墙不动，api 通道专治此坑。
- 包结构：`<名>_学习包/` 下按 `01_资产A/`、`02_资产B/` 分子目录 + `README_学习包说明.md`（列目录内容、接新机步骤、脱敏说明、包外依赖路径）。
- **发 GitHub + 一键安装器**（用户要「建个 bots 文件夹让另一个 Hermes 直接装」时）：包体进 `bots/` 子目录推到 public repo，根下附 `install_bots.py` 安装器 + `README.md`。安装器要做**路径自适应**：`--home=` 显式参数最高优先级（**绝不静默回退**：解析到就 makedirs 后直接用，路径不存在也照建），没给才自动定位（HERMES_HOME 环境变量 > 脚本向上找 > 常见位置）。把包内占位符替换成目标机实际路径，已有文件不覆盖/只补缺、jobs.json 去重并集合并（幂等可重跑）。安装器落点可另配 `paths.json`。注意：安装器向上找 home 的逻辑若跑在源机自己会命中源 home——测试时装到空目录，用 `--home=` 指过去，别误写源机。详见 `references/github-installer-delivery.md`。
- **加密客户专包**（用户要「单独做个文件夹给需要的客户装」时）：从全量包切子集（点名的 profile + 按关键词筛的 cron 任务 + 共享技能，剔掉无关内容线），出 AES 加密 7z，密码单独存本地 txt 永不上仓；交付件用 .gitignore 挡在 public repo 外。py7zr 构造时传密码、密码卫生、子集筛选口径见 `references/github-installer-delivery.md`「加密客户专包」节。
- `python3 shutil.make_archive` 出同名 zip 放在包同级；zip 用 `MEDIA:` 绝对路径发给用户，包大小在报告里写明。
- 对方接机三件事：拷 profile 目录（或不建 profile 直接读技能学习）、config.yaml 空 key 位填对方 key + .env 配 key_env 变量、补包外引擎/数据路径。

## Verification
- 包内 `grep -rnE "sk-[A-Za-z0-9-]{20,}"` 零命中且 config.yaml api_key 全 `''`/指纹；README 存在且含接机步骤；`du -sh` 总量符合预期（profile 级学习包通常 <10M，超了多半误拷了 bundled 技能或缓存）；成品块里混入的其他内容线文件已清零。
- **校验用纯 Python 扫描而非 grep 管道**：`E:\\workbuddy` 这类含反斜杠的模式进 shell 管道会反复误报/漏报。写个 `scan()` 遍历包内文本文件逐 pattern 匹配，一次跑出真 key/手机号/账号/账户号/未抽象路径各自命中数，全 0 才收工。写校验脚本两个坑：① pattern 清单要加「内嵌 git 凭证」（`x-access-token:` 后跟 ≥10 字字符集）一条，专拦 .git 漏网；② 形似令牌字符集的字符类（如 `[A-Za-z0-9_-]`）在落盘时可能被写路径篡改成 `***`（运行报 `multiple repeat`）——正则用短串拼接构造（`"[A-Z" + "a-z0-9" + "_-]{10,}"`），且跑脚本前用 `od -c` 核对磁盘上正则行的实际字节是否完整，不要凭回显/traceback 源码判断。
- 安装器跑通验收：在**空目录**（非源 home）实测一遍，确认「全已存在无新内容」或正确补缺，且没把占位符/数据写进源机。
