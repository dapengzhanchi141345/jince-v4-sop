# 🛠️ 专家团全量打包 · 迁移导入与学习指南

> 生成日期：**2026-09-20** ｜ 资产来源：`C:\Users\ASUS\.workbuddy\plugins\marketplaces\my-experts`
> 规模：**39 个专家 / 178 个子代理 Agent**
> 用途：把李老师的全部 WorkBuddy 专家团迁移到另一个账号/另一个智能体，并让其全面掌握。

---

## 📦 交付物清单

| 文件 | 内容 | 用途 |
|---|---|---|
| `01_专家团核心包_my-experts.zip` | 39 个专家包完整资产：`plugin.json` / `agents`（178 个 Agent 提示词）/ `avatars` / 内嵌技能 / `references` / 市场注册表 | **主资产**，还原专家市场 |
| `02_依赖技能包_dependency-skills.zip` | 专家运行外部依赖技能：`calc-bazi`、`teaching-visualization`、`agnes-ai-support`、`physics-grader-workflow`、`exam-grading-workflow`、`it-courseware-optimize`、`pptx-zh-courseware` | 配套技能 |
| `03_专家团全景学习手册.html` | 深色主题可视化手册：专家卡片、团队阵容、路由速查表 | 给人看的速览（双击打开） |
| `04_专家团精读手册.md` | 同名精读版（Markdown，约 26K 字符） | ⭐ **直接喂给目标 AI 学习全文** |
| `05_专家元数据.json` | 机器可读全量清单（39 专家的名称/版本/成员/标签/入口提问/资源清单） | 供程序化导入或核对 |
| `06_学习资料包_轻量版.zip` | 上面 00/03/04/05 四份文档的压缩包（约 42KB） | ⭐ **只想让 AI 学习、不需要还原专家包时，直接发这个** |
| `_打包脚本_可复用/` | 本次打包用的 4 个 Python 脚本（元数据抽取 / 手册生成 / HTML 生成 / 压缩打包） | 下次更新打包时直接重跑 |

---

## 🚀 导入步骤（Windows）

### 第 1 步：还原专家核心包
1. 打开目标账号配置目录：`C:\Users\<新账号用户名>\.workbuddy\plugins\marketplaces\`
2. 将 `01_专家团核心包_my-experts.zip` **解压到该目录**，得到 `my-experts\` 文件夹
   - ✅ 目标结构：`...\marketplaces\my-experts\plugins\<各专家目录>\`
   - ✅ 同时应存在：`...\marketplaces\my-experts\.codebuddy-plugin\marketplace.json`
3. **重启 WorkBuddy**
4. 打开左侧「专家中心 → 我的专家」，应能看到全部 39 个专家团

### 第 2 步：还原依赖技能
1. 打开目标账号技能目录：`C:\Users\<新账号用户名>\.workbuddy\skills\`
2. 将 `02_依赖技能包_dependency-skills.zip` 解压进去
3. ⚠️ **Agnes API Key 需重新配置**（本包已剔除任何密钥）：
   - 把新账号的 Key 写入 `C:\Users\<新账号用户名>\.workbuddy\skills\agnes-ai-support\.agnes-key`
   - 格式：`AGNES_API_KEY=sk-xxxx`

### 第 3 步：让目标 AI 学会
把 `04_专家团精读手册.md` 的内容发给目标 AI，或直接告诉它「读取该文件」。AI 即可掌握：
- 全部专家的职责分工与召唤方式（`@专家名`）
- 每个专家的团队内部成员构成与头衔
- 任务路由铁律与路由速查表
- 各专家「试试这样问」的入口提问

> 💡 只做「学习」不做「还原」时，直接把 `06_学习资料包_轻量版.zip`（42KB）发过去即可，无需传 106MB 的专家包。

---

## 🗂️ 专家团全景一览（39 位）

| 类别 | 专家（显示名 / 目录名） |
|---|---|
| 🧬 **学科教学主团 ×10** | 万物生 `bio-master`、炼金士 `chem-master`、锦心子 `chinese-master`、通语者 `english-master`、山海客 `geo-master`、史鉴君 `history-master`、明辨君 `morality-master`、数算子 `math-all-domain`、格物君 `physics-omnibus`、码智君 `it-edu-team` |
| ✅ **阅卷评分官 ×10** | 生阅卷 `bio-grader`、化阅核 `chem-grader`、文阅卷 `chi-grader`、英阅卷 `eng-grader`、地阅评 `geo-grader`、史阅评 `his-grader`、德阅判 `mor-grader`、数阅卷 `math-grader`、格阅卷 `physics-grader`、信阅卷 `it-grader` |
| 🔬 **学科辅助与专项 ×4** | 万物生·基础 `bio-basics`、万物生·进阶 `bio-pro`、万物生·前沿 `bio-frontier`、色彩设计大师 `color-design-master` |
| 🀄 **玄学命理 ×2** | 天机阁 `tianji-ge`（10 宗师）、命理排盘师 `bazi-calculator` |
| ⚕️ **医疗健康 ×1** | 岐黄医典 `qihuang-medical`（8 专家） |
| 💹 **财会与金融 ×3** | 算经阁 `suan-jing-ge`（9 专家）、金策宗师团 `goldstrategy-guild`（9 角色）、MT5 EA 编程专家 `mt5-ea-expert` |
| 🏫 **教育行政与教科研 ×3** | 教务智能体 `education-admin`（19 部门/63 模块）、青云梯 `teacher-promotion-filling`、格物致知科研智库 `gewu-zhidao` |
| 🎓 **考研与教育IP ×2** | 研枢考研专家团 `yan-shu-kaoyan`（27 子代理，覆盖公共课+14 门类）、教联中枢 `jiao-lian-zhong-shu` |
| 🎬 **媒体创作与娱乐 ×4** | 视频创作团 `video-crew`、音律工坊 `music-craft-studio`、弈谋阁 `yimou-pavilion`、电子书转电影 `ebook-to-movie` |

> 另有 `it-edu-team_v5_backup`（信息科技团旧版备份目录，随包附带，导入后可删除）。

---

## ⚠️ 注意事项

1. **账号隔离 / 无密钥**：专家包内**不含任何账号密钥**，已全量扫描确认无 `sk-` 泄漏；Agnes Key 需新账号自行配置。
2. **本机双账号**：若两个账号在同一台电脑，直接复制 `marketplaces\my-experts` 与所需 `skills` 目录即可，无需解压。
3. **跨机器迁移**：请用本 zip 压缩包方式复制，避免上万个头像小文件直接拷贝缓慢。
4. **版本备份**：`it-edu-team_v5_backup` 为旧版备份，如不需要可在导入后删除。
5. **专家市场刷新**：若专家中心未显示，检查 `.codebuddy-plugin\marketplace.json` 是否完整解压，并重启 WorkBuddy。

---

*打包由 WorkBuddy 自动完成 · 再次更新打包时重新执行即可*
