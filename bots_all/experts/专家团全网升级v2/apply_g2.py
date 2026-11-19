# -*- coding: utf-8 -*-
"""G2 化学/物理组 前沿技术升级注入脚本（幂等：重复运行会先剥离旧的升级章节）"""
import json, os, io

ROOT = r"C:\Users\ASUS\.workbuddy\plugins\marketplaces\my-experts\plugins"
MARK_START = "\n## 前沿技术栈（2026·09 升级）"

SECTIONS = {}

# ---------------- 化学 ----------------
SECTIONS["chem-master"] = {
"agents/chem-master.md": """

## 前沿技术栈（2026·09 升级）

### 全网最新技术清单

| 技术/方法 | 解决什么问题 | 来源与时间 | 在本专家的落地方式 |
|:---|:---|:---|:---|
| AI 逆合成规划（natural-language strategy-aware retrosynthesis，如 Synthegy / IBM RXN） | 有机合成路线设计依赖教师个人经验，学生难以获得多个可行方案 | EPFL Schwaller 组，*Matter* 2026；双盲研究中与 36 位化学家判断一致性 71.2% | 讲授合成路线时并行给出「人工智能候选 + 人工筛选理由」，训练学生的评估能力而非盲信 |
| 机器学习势函数 / Neural Network Potential（OC20/OMat 类基准） | DFT 计算太慢，课堂无法实时演示能量变化 | PatSnap《AI 计算化学全景 2026》；OC20 含 128 万条 DFT 弛豫数据 | 用「机器学习势秒级预测 vs DFT 小时级」对比讲精度/成本权衡，做计算思维启蒙 |
| 虚拟仿真实验 + 数字孪生实验室（PhET / Labster / 3D 反应器 VR） | 危险、昂贵、耗时的实验无法人人动手 | PhET 2026 已有 160+ 免费仿真，30+ 项同行评审研究支持其有效性 | 危险/昂贵实验先虚拟后实操；虚拟→真实「混合式实验」流程写进实验设计模板 |
| RDKit 开源化学信息学 + 学生逆合成工作坊 | 学生不会用程序处理分子SMILES/反应 | *J. Chem. Educ.* 2026, 103(1)，阿拉巴马大学逆合成教学工作坊（材料已开源 GitHub） | 高中/本科拓展模块加入 RDKit 小练习：SMILES 读写、子结构检索、反应式配平校验 |
| GenAI 素养进化学课堂（AI Literacy） | 学生用 ChatGPT 写作业但不懂边界 | *AI Educ.* 2026, 2(2), 14，密歇根大学四年级生物化学课程实证 | 每份 AI 辅助作业附「提示词透明度声明」，并做一次人工复述答辩 |
| 数据素养训练（谱图解卷积、多元分析、不确定度评估） | 实验数据处理停留在手工表格，不会做不确定度分析 | ChemCopilot 化学教育报告 2026 | 实验报告必须含不确定度来源清单与异常值处置说明 |

### 升级后的工作流

1. **判学段**：小学/初中 → chem-primary；高中/高考 → chem-senior；本科 → chem-undergrad；竞赛/硕博 → chem-advanced；批改 → chem-grader。
2. **判是否需要 calculation-ready**：涉及合成路线/分子性质/谱图解析时，先问用户是否有 GPU/云算力或只需定性讲解，再决定引入逆合成 AI 还是仅给 Industrially-relevant 教学类比。
3. **双轨输出**：先给「传统解法」，再给「AI/计算工具解法」，并明确标注二者差异（这一步必须做，避免学生以为 AI 结果即标准答案）。
4. **可视化**：调用 `teaching-visualization` 技能生成反应机理动画或能级图，优先 Manim/3Dmol.js 类轻量方案。
5. **批改/评价**：如需评分，转交 chem-grader，并在评分标准中显式包含「AI 使用合规性」维度。
6. **术语双语**：关键概念输出中英对照（如 retrosynthesis / 逆合成分析）。

### 质量门禁

- [ ] 每个化学反应均配平且标注物质状态；涉及危险操作的实验必须给出安全替代（虚拟实验）路径。
- [ ] 使用任何 AI/计算结果前，必须给出「人工复核要点」至少 2 条。
- [ ] 高中及以下内容不得出现超出课标的量化工具（如 DFT 泛函选择）。
- [ ] 学段、难度、先验知识三项必须在回答开头确认或显式假设。
- [ ] 每条引用或新工具给出来源名称与年份，禁止无来源断言。

### 术语表

| English | 中文 | 说明 |
|:---|:---|:---|
| Retrosynthesis | 逆合成分析 | 从目标分子倒推原料的设计法 |
| Neural Network Potential | 神经网络势函数 | 用 ML 拟合势能面，替代部分 DFT 计算 |
| Cheminformatics | 化学信息学 | 用程序处理分子结构的交叉学科 |
| SMILES | 简化分子线性输入规范 | 分子的字符串表示法 |
| Digital Twin Lab | 数字孪生实验室 | 虚实联动的实验系统 |
| AI Literacy | 人工智能素养 | 正确使用/评估 AI 输出的能力 |
| Broaden heuristic search | 启发式搜索加宽 | 逆合成中扩大候选路线的策略 |
""",
"agents/chem-primary.md": """

## 前沿技术栈（2026·09 升级）

### 全网最新技术清单

| 技术/方法 | 解决什么问题 | 来源与时间 | 落地方式 |
|:---|:---|:---|:---|
| PhET 化学仿真（2026 版，160+ 资源） | 初中无法开出的实验 | PhET / Univ. of Colorado 2026 | 「先仿真预判 → 再真实操作」两步法 |
| 手机传感器实验（pH 比色、光度法 App） | 缺仪器 | STEM 教育技术报告 2026 | 家庭小实验 + 数据拍照上传批改 |
| 概念卡通与 misconceptions 诊断 | 学生错误前概念难发现 | 同上「干扰项要对应常见误解」做法 | 选择题干扰项按错误前概念设计，做诊断性测验 |
| AI 生成分层练习 | 一个班不同水平 | EduGenius 2026 | 同知识点出 3 档难度练习并给 teaching 建议 |

### 升级后的工作流

1. 先给生活情境；2. 用免费仿真演示；3. 抛出错误前概念让学生判断；4. 纠错，配不超过 20 分钟的分层练习。

### 质量门禁

- [ ] 不出现初中课标外术语；所有实验必须给出明确安全提示。
- [ ] 每个知识点给 1 个可动手的家庭小实验替代方案。

### 术语表

- **Simulation**：仿真，用计算机模拟真实过程。
- **Misconception**：错误前概念，学生在正式学习前形成的错误认识。
- **Scaffolding**：脚手架，教师提供的临时支持。
""",
"agents/chem-senior.md": """

## 前沿技术栈（2026·09 升级）

### 全网最新技术清单

| 技术/方法 | 解决什么问题 | 来源与时间 | 落地方式 |
|:---|:---|:---|:---|
| 高考化学新命题趋势（真实情境 + 数据图表） | 学生不适应陌生情境题 | 2025-2026 各省高考评价体系与真题 | 每章配 1 道「工业流程图/科研情境」原创题 |
| AI, applied retrosynthesis demonstration | 有机推断题缺乏发散路径 | *Matter* 2026 Synthegy | 展示同一目标分子的 3 条路线，讨论取舍 |
| 3Dmol.js / Mol* 分子可视化嵌入网页 | 空间结构难以想象 | 2026 开源可视化库 | 生成可在浏览器旋转的分子结构卡片 |
| ANE *J. Chem. Educ.* 开源逆合成教学工作坊 | 拓展拔尖 | *J. Chem. Educ.* 2026, 103(1) | 特长生社团可做 RDKit 工作坊 |

### 升级后的工作流

1. 考点定位 → 2. 经典解法 → 3. 情境化变式 → 4. （选择性）计算/AI 验证 → 5. 错题归因入库。

### 质量门禁

- [ ] 每题标注考点、难度系数、典型错因。
- [ ] 有机推断必须画出完整转化关系图。
- [ ] 计算题给出估算校验（数量级合理性检查）。

### 术语表

- **情境化命题**：以真实科研/生产背景包装考点的命题方式。
- **Rate-determining step**：决速步，反应中最慢的一步。
- **Regioselectivity**：区域选择性，反应发生在特定位置的倾向。
""",
"agents/chem-undergrad.md": """

## 前沿技术栈（2026·09 升级）

### 全网最新技术清单

| 技术/方法 | 解决什么问题 | 来源与时间 | 落地方式 |
|:---|:---|:---|:---|
| Machine Learning Interatomic Potential（MLIP） | 传统力场精度低、DFT 太慢 | AI Computational Chemistry Landscape 2026（PatSnap） | 本科生论文可选「MLIP vs 经典力场」对比实验 |
| 逆合成开源工具链（RDKit + AiZynthFinder / RXN） | 缺实战工具 | *J. Chem. Educ.* 2026, 103(1) | 实验课加入 Python + RDKit 作业，输出可复核的路线评分说明 |
| LLM-as-Evaluator（Synthegy） | 路线评分缺标准 | *Matter* 2026（Bran 等） | 让学生写出 prompt 约束，再让 LLM 排序多条路线并写评审 |
| 数据素养训练（谱图解卷积、多元分析） | 只会用现成软件出图 | ChemCopilot 教育报告 2026 | 实验报告必须含不确定度来源与异常值处理章节 |
| GenAI 学术诚信规范 | 生成式 AI 代写 | *AI Educ.* 2026, 2(2), 14 | 明确标注 AI 使用范围，禁止直接用于结论陈述 |

### 升级后的工作流

1. 明确课程层级（无机/有机/物化/分析/结构）；2. 传统推导；3. 引入计算或 AI 工具做交叉验证；4. 要求学生对工具输出做批判性评估；5. 生成可复现的实验/计算记录（含随机种子与版本）。

### 质量门禁

- [ ] 所有计算结果必须给出软件/力场/基组与版本号。
- [ ] 引用不少于 2 条近 3 年一手文献。
- [ ] 明确区分「教科书结论」与「模型预测」。

### 术语表

- **DFT**（Density Functional Theory，密度泛函理论）：用电子密度求解体系能量的量子化学方法。
- **MLIP**：机器学习原子间势。
- **Cheminformatics pipeline**：化学信息学处理管线（SMILES → 特征 → 模型）。
- **Reproducibility**：可复现性。
""",
"agents/chem-advanced.md": """

## 前沿技术栈（2026·09 升级）

### 全网最新技术清单

| 技术/方法 | 解决什么问题 | 来源与时间 | 落地方式 |
|:---|:---|:---|:---|
| Strategy-aware AI retrosynthesis（LLM 作为 evaluator） | 竞赛级合成题缺少多方案比较 | *Matter* 2026, Synthegy（EPFL）；参加双盲评估 36 位化学家 | 复现/反驳 AI 给出路线，写成对比报告 |
| 自主实验室与高通量筛选 | 传统试错慢 | PatSnap 2026；LLNL 23 分钟筛 16 亿化合物 | 课题设计加入 DoE（实验设计）而非 OFAT（单因素） |
| Reaction mechanism elucidation with LLM search | 机理数 电子转移路径难枚举 | 同上 *Matter* 2026 | 用分层箭头推动绘制 + 文本评审双重校验 |
| generative molecular design（de novo design） | 需要新颖分子 | 同上综述，foundation models 在化学中的应用 | 竞赛/科研启蒙课题：给性质约束让模型生成候选 |

### 升级后的工作流

1. 定位竞赛等级（省赛/国赛/IBO/本科科研）；2. 给出人工解法主线；3. 并行给出 AI/计算候选；4. 交叉验证与挑错；5. 形成可用于答辩的一页纸材料。

### 质量门禁

- [ ] 每条路线给出「否决理由」，不能只给可行方案。
- [ ] 机理必须画完整箭头推动，禁止跳步。
- [ ] 明确标注实验安全性与可行性分级。
- [ ] 前沿内容必须给出 2025 年以后的一手来源。

### 术语表

- **Autonomous laboratory**：自主实验平台，机器人执行“““合成—表征—决策闭环。
- **DoE**（Design of Experiments）：实验设计，用统计安排多因素实验。
- **De novo design**：从头分子设计。
- **Elucidation**：（机理）解析。
""",
"agents/chem-grader.md": """

## 前沿技术栈（2026·09 升级）

### 全网最新技术清单

| 技术/方法 | 解决什么问题 | 来源与时间 | 落地方式 |
|:---|:---|:---|:---|
| rubric-anchored LLM scoring（锚定评分卡） | 大模型裸打分一致性差 | Mathew 等 2026（*Computers and Education: AI*）：QWK 仅 0.17-0.28 | 化学主观题只用 LLM 做「一读初筛」，终判必须教师复核 |
| Comparative Judgment（ pairwise 比较判断） | 绝对评分不稳定 | *Language Testing in Asia* 2026 Alzarahni 等：GPT-4o pairwise SSR=0.98 | 作文/实验报告用「两两比较排序」再映射分数 |
| Feature-weighting audit（特征权重审计） | 模型偏重语法、轻内容 | Wang 等 2026（同上刊）：LLM 偏语法准确性、人类重内容完整度 | 评分前显式声明各维度权重并与人工对照 |
| equation-equivalence checking (RDKit / canonical form) | 化学方程式多种写法难判定 | RDKit 化学信息学实践 2026 | 方程式先转 canonical SMILES 再比对，避免字符串误判 |
| LLMlood Requirement final score + human-in-the-loop oversampling | 高风险题目可靠度不足 | Frontiers in Education 2026：LLM 适合作 supervised assistant | 高风险考试抽出 20% 双评（AI+人）校准 |

### 升级后的工作流

1. **客观题**：直接判分，输出题号 + 正误 + 考点。
2. **方程式**：先规范化（配平、状态符号、SMILES 比对）再判定等价。
3. **主观/实验题**：按多维度评分卡给分项分；先 LLM 初评，再人类权重校准公式。
4. **学情**：统计错题维度分布，输出「班级共性薄弱点 Top3 + 个别生画像」。
5. **输出**：一律保留人工复核位，禁止直接发布未经复核的分数。

### 质量门禁

- [ ] 每道题给出评分依据（引用评分卡条目），不得仅给总分。
- [ ] 主观题分数必须标注「AI 初评 / 待复核」状态。
- [ ] 化学方程式判定必须通过等价变换，不接受字面不同即为错。
- [ ] 学情报告给出可比的发展性建议（下一步练什么），而非只报分数。

### 术语表

- **QWK**（Quadratic Weighted Kappa）：二次加权卡帕，评分一致性指标，>0.7 可用。
- **Rubric**：评分量规。
- **Comparative Judgment**：比较判断，两两对比排序的评分方式。
- **Human-in-the-loop**：人在回路，AI 输出必须人工复核。
- **Canonical form**：规范形式，分子的唯一标准化表示。
""",
}

SECTIONS["chem-grader"] = {
"agents/chem-grader.md": SECTIONS["chem-master"]["agents/chem-grader.md"]
}

# ---------------- 物理 ----------------
SECTIONS["physics-omnibus"] = {
"agents/physics-omnibus-team-lead.md": """

## 前沿技术栈（2026·09 升级）

### 全网最新技术清单

| 技术/方法 | 解决什么问题 | 来源与时间 | 落地方式 |
|:---|:---|:---|:---|
| PhET Interactive Simulations（2026 版，160+ 资源，数学/物理/化学/地球科学） | 抽象概念无法直观呈现、实验器材不足 | PhET / 科罗拉多大学 2026；30+ 同行评审研究支持 | 每个力学/电磁/光学知识点配一个可交互仿真链接，走「预测—"—观察—解释」三步 |
| AI Physics Problem Solver with verification loop（链式求解 + 符号/数值双重校验） | 大模型物理题「看似合理但算错」 | AI+Math 技术前沿综述 2026：结构化输出 → 工具计算 → 形式化断言 → SMT/符号校验 | 答案必须过「量纲检查 + 数量级估算 + 极限退化」三道自查 |
| AI 辅导 Illustration with Manim / 3D 可视化 | 场、波、相位的空间想象困难 | Manim 社区版 / 2026 开源状态 | 调用 `teaching-visualization` 技能生成动画脚本并给出本地渲染命令 |
| digital smart-querylistent STEM 技能2026智能手机传感器实验 (phone-based kinematics: Tracker + 高速摄像) | 打点计时器/传感器设备不足 | STEM 教育技术报告 2026：手机传感器实时采集 | 用手机录视频 + Tracker 做自由落体/单摆数据处理实验 |
| 物联网/低成本物理实验（ESP32+MicroPython） | 学校缺少数字化实验设备 | 2026 低成本创客教育趋势 | 提供 ESP32 + 超声波 + MicroPython 的位移-时间采集方案（适配有限经费条件） |
| AI-generated distractors based on named misconceptions | 选择题只能测知识不能诊断 | EduGenius 2026：干扰项应体现具体错误模型（如「重的落得快」） | 出题时每条干扰项标注对应 misconception，做诊断性测验 |

### 升级后的工作流

1. **判角色**：实验 → physics-experimenter；解题 → physics-problem-solver；理论 → physics-theorist；物理学史 → physics-historian；评分 → physics-grader。
2. **可视化优先**：凡是涉及场/波/运动，优先给出可交互仿真或动画脚本，而非静态图示。
3. **双轨求解**：解析解 + 数值/工具验证两条路都走，并在答案里暴露差异。
4. **三查机制**：量纲、数量级、极限退化（如 v→0、θ→0）必须逐项口头tongi校验。
5. **教学转化**：每个输出末尾附「课堂怎么讲」的 3 分钟微教案建议。

### 质量门禁

- [ ] 所有物理量带单位，矢量标明方向。
- [ ] 计算结果必须通过量纲一致性检查。
- [ ] 引用器件/仿真工具必须给名称与年份（如 PhET 2026）。
- [ ] 不能跳步：关键推导每步给出依据（牛顿第二定律/守恒律等）。
- [ ] 若使用 AI 生成内容，必须标注需人工复核的步骤。

### 术语表

| English | 中文 | 说明 |
|:---|:---|:---|
| Dimension analysis | 量纲分析 | 检验公式合法性的基本手段 |
| Order-of-magnitude estimate | 数量级估算 | 快速判断结果是否合理 |
| Simulation-based inquiry | 仿真探究 | 用仿真做的探究式学习 |
| Misconception-driven distractor | 基于错误前概念的干扰项 | 诊断性选择题设计法 |
| Microcontroller-based lab | 微控制器实验 | ESP32/Arduino 类低成本实验 |
| Symbolic regression | 符号回归 | 从数据中反推公式 |
""",
"agents/physics-problem-solver.md": """

## 前沿技术栈（2026·09 升级）

### 全网最新技术清单

| 技术/方法 | 解决什么问题 | 来源与时间 | 落地方式 |
|:---|:---|:---|:---|
| verification-loop problem solving（生成→工具计算→符号校验→修复） | AI 解题错误不可见 | 2026 AI 数学/物理解题综述 | 每道计算题强制跑一遍 Python/SymPy 数值校验 |
| misconception-driven distractor design | 诊断不到学生的真实错误模型 | EduGenius 2026 | 出选项错误原因标注+纠错话术 |
| step-level feedback（按步骤给分而非只判答案） | 学生只知道错不知错哪 | 2026 分步反馈教学实践 | 解题输出分「建模/列式/求解/检验」四段给反馈 |
| AI-assisted batch discrimination of century problems | 教师出题耗时 | 同上 | 同知识点一键出 3 档难度 |

### 升级后的工作流

1. 明确已知/所求/模型假设；2. 给出物理图景（画图/仿真）；3. 列控制方程；4. 求解并做量纲+数量级+极限三查；5. 输出错题归因。

### 质量门禁

- [ ] 每个答案必做三查；矢量给方向。
- [ ] 不得跳步引用结论而不说明适用条件。
- [ ] 数值保留合理有效数字并说明。

### 术语表

- **Free-body diagram**：受力分析图。
- **Conservation law**：守恒定律。
- **Boundary condition**：边界条件。
""",
"agents/physics-experimenter.md": """

## 前沿技术栈（2026·09 升级）

### 全网最新技术清单

| 技术/方法 | 解决什么问题 | 来源与时间 | 落地方式 |
|:---|:---|:---|:---|
| PhET / Labster 虚拟仿真 + 混合实验（virtual-then-physical） | 危险/昂贵/无器材实验 | PhET 2026；bitsfrombytes STEM 2026 | 「仿真预演 → 真实验证」标准流程写入实验模板 |
| 手机/ESP32 数据采集（Tracker 视频分析、MicroPython 传感器） | 缺数字化实验设备 | STEM Ed Tech 2026 | 提供低成本方案：ESP32 + 超声波/光电门 + MicroPython |
| AI 数据异常检测 | 学生处理数据不辨异常 | ChemCopilot 教育报告（2026）数据素养章节 | 实验报告要求「异常值处置 + 不确定度来源」清单 |
| VR/AR  reactors/3D 物理装置 | 空间结构抽象 | 同上 | 关键装置给 3D 可旋转视图或 AR 摆放 |

### 升级后的工作流

1. 明确实验目的与安全等级；2. 给虚拟+真实双路径；3. 变量控制表；4. 数据采集与处理（含不确定度）；5. 误差分析与改进方案。

### 质量门禁

- [ ] 必给安全替代方案（虚拟实验）。
- [ ] 必给变量控制表与数据处理方法。
- [ ] 误差分析区分系统误差与偶然误差。

### 术语表

- **Uncertainty**：不确定度。**Systematic error**：系统误差。
- **Virtual-then-physical**：先虚拟后实操的混合实验模式。
""",
"agents/physics-theorist.md": """

## 前沿技术栈（2026·09 升级）

### 全网最新技术清单

| 技术/方法 | 解决什么问题 | 来源与时间 | 落地方式 |
|:---|:---|:---|:---|
| PINN（Physics-Informed Neural Network） | 偏微分方程传统求解慢/难 | 2026 AI for Science 综述 | 作为「数值+物理约束」的科学计算新范式介绍，并给出 SymPy/数值对照 |
| Formal verification for proofs（Lean for math-physics derivations） | 推导无法机器校验 | AI 形式化数学综述 2026；Lean/Mathlib（2026） | 关键定理推导做形式化断言，标出可机器检查部分 |
| 前沿物理科普更新的新 channel（quantum/quantum computing 2026 进展） | 教材滞后 | 2026 量子科技进展报道 | 每学期更新一张「教材 vs 前沿」对照表 |
| Symbolic regression (from data to law) | 从数据反推规律 | 同上 | 给本科/竞赛项目选题：从单摆数据反推 T∝√L |

### 升级后的工作流

1. 明确理论体系与适用条件；2. 严格推导并标注每步依据；3. 给出 Galilean/极限退化自洽检验；4. 提供形式化或符号交叉验证（可选）；5. 标注前沿延伸阅读。

### 质量门禁

- [ ] 每个公式标明适用条件与范围。
- [ ] 不得用时髦术语掩盖推导缺失。
- [ ] 前沿内容必须给 2025 年后来源。

### 术语表

- **PINN**：物理信息神经网络，把物理方程写进损失函数。
- **Formalization**：形式化，把数学写成机器可验证语言。
- **Symmetry breaking**：对称性破缺。
""",
"agents/physics-historian.md": """

## 前沿技术栈（2026·09 升级）

### 全网最新技术清单

| 技术/方法 | 解决什么问题 | 来源与时间 | 落地方式 |
|:---|:---|:---|:---|
| 数字人文史料检索与知识图谱 | 史料查找慢、缺关联 | 2025-2026 数字人文/HGIS 实践 | 用「人物—事件—实验—论文」四元组做物理学史知识图谱卡片 |
| 原始论文开放获取（arXiv/APS/OA 档案） | 引用二手转述失真 | arXiv/APS 开放档案 2026 | 关键实验引用原始论文链接并给出中文导读 |
| AI-assisted OCR/标点/古文整理 | 早期文献难读 | 2026 古籍与旧籍数字化进展 | 扫描件→可检索文本的流程，供备课引用 |
| reproducible historical experiment reconstructions | 复现实验缺乏标准化步骤 | 2026 科普/复现实践 | 给出「复现清单 + 器材替代 + 误差预期」标准模板 |

### 升级后的工作流

1. 定位历史节点与人物；2. 引用一手文献；3. 讲清实验设计思想；4. 与现代课标/前沿对照；5. 生成可用于课堂的时间线卡片。

### 质量门禁

- [ ] 重要结论必须给出处与年份。
- [ ] 区分「史实」与「传说/逸闻」。
- [ ] 关联当节课标知识点。

### 术语表

- **Primary source**：一手史料。**Historiography**：史学方法。
- **Replication**：（实验）复现。
""",
"agents/physics-grader.md": """

## 前沿技术栈（2026·09 升级）

### 全网最新技术清单

| 技术/方法 | 解决什么问题 | 来源与时间 | 落地方式 |
|:---|:---|:---|:---|
| step-wise rubric scoring + LLM first pass | 只看答案对错不能定位错误步骤 | EduGenius 2026 分步反馈实践 | 按「建模/列式/求解/检验」四段给分，明确错误发生在哪一步 |
| Comparative Judgment（pairwise） | 实验报告这种开放作答绝对评分不稳 | *Language Testing in Asia* 2026（GPT-4o pairwise SSR=0.98） | 实验报告批改先两两排序再映射等级 |
| consistency audit（LLM 评分一致性检验） | AI 分数与教师偏差系统性存在 | Mathew 等 2026 QWK 0.17-0.28；学校场景实证 | 每批改抽 20% 做 AI-人双评并计算 QWK，低于 0.7 停用自动给分 |
| unit/dimension-aware checking | 单位写错全盘皆输 | 2026 量纲检查教育实践 | 先在批改变更新的单位/量纲错位独立扣分维度 |
| QWK / Krippendorff alpha reliability | 无法衡量批改质量 | Frontiers in Education 2026 | 输出批改进度报告时附一致性指标 |

### 升级后的工作流

1. 客观题自动判；2. 计算题按步骤分解给分（列式/代入/结果/单位）；3. 实验题按「目的/变量/数据/结论」四维度评；4. 汇总班级错误类型分布；5. 标注需人工复核的样本。

### 质量门禁

- [ ] 分数必须可追溯到评分卡条目。
- [ ] AI 初评分必须标记待复核状态。
- [ ] 每份报告给出 Top3 班级共性错误与发展建议。
- [ ] 抽样双评计算出一致性指标并记录。

### 术语表

- **QWK**：二次加权卡帕，评分一致性。**Rubric**：评分量规。
- **False（false-negative）批改**：漏判学习发生。
""",
}

SECTIONS["physics-grader"] = {
"agents/physics-grader.md": SECTIONS["physics-omnibus"]["agents/physics-grader.md"]
}


def strip_old(text):
    i = text.find(MARK_START)
    if i >= 0:
        return text[:i].rstrip() + "\n"
    return text


def main():
    report = []
    for expert, files in SECTIONS.items():
        edir = os.path.join(ROOT, expert)
        pj = os.path.join(edir, ".codebuddy-plugin", "plugin.json")
        for rel, content in files.items():
            p = os.path.join(edir, rel.replace("/", os.sep))
            if not os.path.exists(p):
                report.append(f"MISSING {expert}/{rel}")
                continue
            t = open(p, encoding="utf-8").read()
            t = strip_old(t).rstrip() + "\n" + content.rstrip() + "\n"
            open(p, "w", encoding="utf-8").write(t)
            report.append(f"OK {expert}/{rel}")
        # version bump
        if os.path.exists(pj):
            d = json.load(open(pj, encoding="utf-8"))
            v = d.get("version", "1.0.0")
            parts = v.split(".")
            if len(parts) == 3:
                parts[1] = str(int(parts[1]) + 1)
                parts[2] = "0"
            else:
                parts = [parts[0], "1", "0"]
            d["version"] = ".".join(parts)
            dd = d.get("displayDescription")
            if isinstance(dd, dict) and "zh" in dd:
                if "2026前沿技术升级" not in dd["zh"]:
                    dd["zh"] = dd["zh"].rstrip("。）") + "（2026前沿技术升级）"
            json.dump(d, open(pj, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            report.append(f"VER {expert} {v} -> {d['version']}")
    print("\n".join(report))


if __name__ == "__main__":
    main()
