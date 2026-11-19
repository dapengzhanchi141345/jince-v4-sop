# 发 GitHub + 一键安装器交付法（hermes-asset-port 分支）

当用户要「在我的 GitHub 建个 bots 文件夹，让另一个 Hermes 直接克隆装上」时，学习包不止出 zip——出**可 clone 的 public repo + 路径自适应安装器**。本分支只记接机侧怎么做；打包脱敏见 SKILL.md 主体。

## 仓库结构
- public repo，根下就一个 `bots/` 子目录（= 学习包，按 profile 分子目录 + manifest.json）。
- repo 根还放 `install_bots.py`（安装器）+ `README.md`（脱敏清单 + 接机三步 + 占位符说明表）。
- `gh repo create <user>/hermes-bots-port --public`；`git push -u origin master` 后用 `gh api repos/<o>/<r>/contents/bots` 实拉列目录验 27 个 bot 全在（size 字段是惰性的，别拿它当推送成功的证据，contents 列全了才算数）。

## 安装器 install_bots.py 要点
- **路径自适应**：目标 hermes home 按优先级解析——① `--home=` 参数 > ② `HERMES_HOME` 环境变量 > ③ 从脚本位置向上找含 config.yaml/profile.yaml 的目录 > ④ 常见位置（`~/.hermes` 等）。任何一个位置装都能认出来，不写死路径。
- **占位符**：包内绝对路径打包时就抽象成 `{{WORKBUDDY}}`/`{{HERMES_HOME_PARENT}}`/`{{JINCE_ENGINE}}`；安装器把它们替换成目标机实际值，值可被同目录 `paths.json` 覆盖。`default` bot 装进 hermes home 根，其余 profile 装进 `<home>/profiles/<name>/`。
- **幂等合并**：单文件（SOUL/profile/config/.env）缺才补不覆盖；memories/skills 递归补缺；`cron/jobs.json` 按 prompt 前 N 字去重并集合并。跑多少次都不破坏目标机已有数据，这是「可重跑」的核心。
- 装完打印：home 落点、占位符实际值、每 bot 落了哪些新文件、提示去填 `.env` 里的 `<FILL_ME>` key。

## 坑
- **别误装进源机**：安装器「向上找 home」若在源机跑会命中源 home，测试时装到**空目录**并 `--home=` 指过去。实测报告若显示 `[=] 全已存在` 且只补了源机默认 jobs.json 的幂等并集，说明是源机、无损可忽略；但正确验收要在空 home 里跑。
- **`--home=` 显式指定绝不静默回退**：解析到参数就 makedirs 后直接返回该路径，**不要**把它 insert/append 进候选列表再走自动探测（候选里的 HERMES_HOME 环境变量/向上找会抢回源 home；静默装错位置比报错危害大）。旧写法 `cands.insert(0, ...)` 已证伪——环境变量插队、参数被 shell 吃坏时都静默回退源 home。
- **git-bash 传 `--home=C:\...` 会被吃反斜杠**：Python 收到的是 `C:tmpfake-jince`。测试一律用正斜杠 `--home=C:/tmp/x`（安装器内 `replace("/", os.sep)` 归一）；客户在 cmd/双击场景不受影响。传参后先 `python -c "import sys;print(sys.argv)"` 验一次实收值再跑安装器。
- **包 jobs.json（占位符版）合并进活系统 cron = 坏路径 + 同 id 重复**：安装器按 prompt 文本去重，活体版（真实路径）与包版（占位符）文本不同 → 同一 job id 存两份、其中一份路径错。误写进活 home 后修复：按 job id 用「包源占位符替换回本机真实路径」整版还原活体 jobs.json（占位符→本机路径表逐个 replace 后写回），逐文件验 id 零重复、`{{` 残留零命中，原脏版留 `.cleanbak`。金策活系统在跑时这一步是必须的——活 cron 是 30min 循环的执行源。
- **paths.json 定制值统一 `/` 分隔**：写回前 `replace("\\","/")`，避免 Windows 双反斜杠进 JSON/包源。

## 加密客户专包（子集 + 7z 加密，交付件不上公开仓）
用户要「单独做个文件夹，给需要的客户装」时走本子工序（在 public repo 已建好之后）：
1. **子集筛选**：点名的几个 profile 整拷（源已脱敏）；`default` 里只按关键词（业务线名词/节点名）筛出该客户该拿的 cron jobs，无关内容线（如教育日更）全部剔除；共享技能只挑该业务用的（如 mt5 系列）。筛完报告「N/M 条 + 剔了什么」。
2. **独立安装器 `install_<线>.py`**：逻辑同 install_bots.py（占位符替换 + 幂等合并 + `--home` 绝不静默回退），bot 名单硬编码为该子集，包根缺关键 profile 目录直接报错。
3. **加密**：py7zr 密码在**构造时**传——`SevenZipFile(path, mode="w", password=pw, header_encryption=True)`，不是 `z.write(..., encrypt_password=)`（1.x 无此参数，传了直接 TypeError）。另：execute_code 内核解释器 ≠ terminal 的 python，pip 装完要切 terminal 跑脚本。
4. **密码卫生**：`secrets` 生成 12 位、去掉 O/0/I/1/L 易混字符；写进本地独立 txt，**永不上 git、永不进 7z**；发客户时 7z 走文件通道、密码走聊天单独一条。密码文件与 7z 都进仓库 `.gitignore`（模式：`*.7z`、`*_解压密码.txt`、`jince/` 类交付目录）。
5. **验收**：加密包能带密码列出 entries 且关键文件在；子集目录逐类扫 0 泄漏——次级 PII 也要扫：用户名（`ASUS` 类）、msys 路径 `/c/Users/<name>`、文档示例里 `chr(92)` 拼接的本机路径，统一换 `{{USER_HOME}}` 占位并由安装器解析（默认 `os.path.expanduser('~')`）。

## 验收
- 空 home 跑一遍：27 bot 全 `[装]` 出新增（SOUL/profile/memories/skills/cron），不报覆盖告警；`.env` 生成且全是占位符。
- 包体零泄漏：真 key/手机号/微信账号/MT5 账户号/未抽象绝对路径 逐类扫描 0 命中（用 SKILL.md 的纯 Python `scan()`，别用 grep 管道）。
- GitHub 上 `bots/` 目录 contents 实拉齐全，commit 已推 master。
