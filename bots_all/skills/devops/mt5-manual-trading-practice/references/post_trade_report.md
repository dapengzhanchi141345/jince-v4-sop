# 练手后深度复盘与分发（模板）

用户要求：分析要「分析透（≥10 个角度）+ 深度融合学习资料 + 分享（chief/风控官/WorkBuddy/dsh 四路）+ 务必赚到钱」。按此 4 问产出，缺一项就是没做到位。

## 复盘必答 4 问
1. **七层哪层选错**（顺序：先查结构/日型选择，再看单笔盈亏——单笔 −1R 在方程成本内不是错，选错日型才是错）。
2. **机会成本表**（没赚到手的钱）：`动作 | 实际 | 应然 | 差额`。例：对锁时按旧锚平同向腿 → 应然持有到趋势目标价，差额=两价之差×点值。这是复盘的主角，比净盈亏重要。
3. **3 条可检验预测**（次场能验证，进五验队列，同分母统计）。
4. **次日测试日方案**（时点/动作/通过判据/盈利目标与验收线，如「三场连绿」）。

## 实盘×学习资料融合模板（八课式）
每个今日用到的工具出一课：`资料章节（Brooks/Seiden/LTSD/Manson 出处）→ 今日盘面回声（真实价格点位）→ 做单手法（可执行参数）→ 盈亏验证（R 倍数）→ 一句话口诀`。资料底稿：`E:\workbuddy\内容中心\知识库\机构订单交易_深度学习笔记.md` + `机构订单_统一决策模型.md`；产出教学模块存 `E:\workbuddy\内容中心\知识库\`。

## Word 生成要点（详见 docx 技能）
- host venv `D:/jince_sass/.venv/Scripts/python.exe`（python-docx+matplotlib+Pillow 已装）；`env -u PYTHONPATH` 前缀跑。
- 中文 builder 用 python-docx 直接构建；每个 run 设 eastAsia 字体（微软雅黑）；标题走 `doc.add_heading` 才有导航大纲；内层引号用「」防字符串截断；`py_compile` 预检再跑；TOC/PAGE/NUMPAGES 走 fldChar 域（Word 打开时 F9 更新）。
- 图表：matplotlib 注册 msyh 字体防方块字；避免 ✓ 等缺字 glyph。
- 产出后 `docx_read --structure` + `docx_validate` 验证再发。

## 四路分发
- chief / 风控官：message_agent，正文=结果+两条核心教训+11 条清单摘要+3 个文件路径。
- WorkBuddy / dsh：AgentCommons post（中文 BOM .ps1 配方见 agent-commons 技能），投递后 glob `E:/AgentCommons/bus/inbox/<code>/*.json` 核到件，不信 stdout 自报。
- 每条都写「历史回测≠未来收益」口径；教学不荐方向，只教纪律/方法/量化口。
