# 信息科技教学团 (IT Education Team)

基于2022版义务教育信息科技课程标准的全栈教学团队，覆盖初中7-9年级课程设计、Python编程教学、物联网与AI实践、试题命制与竞赛指导。

## 类型

Team 型（多角色协作团队）

## 团队成员

| 角色 | 名字 | 职责 |
|------|------|------|
| 🧑‍🏫 教学总导师（主理人） | 程导思 | 课程设计、教案编写、团队调度、课标准解读 |
| 💻 编程助教 | 柯智码 | Python编程、算法教学、IoT硬件编程、代码审阅 |
| 📝 出题测评官 | 申考衡 | 试题命制、学情分析、作业设计、竞赛模拟 |

## 功能

- **课程设计**：基于2022版课标，覆盖四大模块（互联网应用与创新、物联网实践与探索、人工智能与智能社会、跨学科主题）
- **编程教学**：Python全栈教学（变量到面向对象）、算法（排序/查找）、IoT硬件编程（Micro:bit/Arduino）
- **考核评价**：试卷命制、双向细目表、分层作业、学情分析报告
- **竞赛指导**：NOC、CSP-J/S初赛等竞赛模拟与策略指导

## 使用示例

- "我需要一堂七年级《互联网应用与创新》的优质课教案，包含项目式学习设计"
- "帮我出10道Python基础选择题，附带解析和难度标注"
- "如何设计一个跨学科物联网教学项目？要求融合数据采集与AI分析"

## 头像

| 文件 | 角色 | 状态 |
|------|------|------|
| `avatars/it-edu-team-team-lead.png` | 程导思（教学总导师） | ✅ 已生成 |
| `avatars/ke-code-ta.png` | 柯智码（编程助教） | ⏳ 待生成 |
| `avatars/shen-exam-designer.png` | 申考衡（出题测评官） | ⏳ 待生成 |
| `avatars/team.png` | 团队头像 | ⏳ 待生成 |

如需补充生成剩余头像，请运行 ImageGen 并重命名至对应文件名。
如需替换为自定义头像，要求：
- 格式：PNG（推荐）或 JPG
- 尺寸：512×512 px
- 大小：单张不超过 500KB

## 安装

将专家包目录放到以下路径：

```
~/.workbuddy/plugins/marketplaces/my-experts/plugins/it-edu-team/
```

然后运行注册命令使其在 WorkBuddy 中可见：

```bash
python3 scripts/register_expert.py ~/.workbuddy/plugins/marketplaces/my-experts/plugins/it-edu-team/
```

## 打包分享

```bash
python3 scripts/package_expert.py ~/.workbuddy/plugins/marketplaces/my-experts/plugins/it-edu-team/
```
