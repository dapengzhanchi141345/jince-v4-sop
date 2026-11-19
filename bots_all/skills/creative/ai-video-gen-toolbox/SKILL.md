---
name: ai-video-gen-toolbox
description: 2026 最给力视频生成全谱工具箱。做教育/短剧/数字人视频前查选型与流水线。
---

# AI 视频生成工具箱（2026 全网蒸馏）

做教育视频/口播数字人/短剧/漫剧前，先查本技能选「对的工具组合」，别默认只会 Manim。

## 〇、按场景选工具（决策树，最重要）
| 你要做什么 | 最给力组合 | 备注 |
|---|---|---|
| 数学/科学/代码**过程动画** | Manim（本地渲染，teacher-video-lesson-team 已有） | 精确、可复现、零成本；缺点是纯几何不写实 |
| 真人**口播/出镜**不想露脸 | 数字人：黑狐/腾讯智影/讯飞智作（免费额度）或 HeyGen/D-ID | 中文口型贴合，配 TTS 一键出片 |
| 真人出镜（最自然，冲质量） | 手机自录旁白 + 剪映/课程页背景 | 质感最高，成本=念 14 段 |
| 电影级**写实镜头/B-roll** | Veo 3.1（综合第一）/ Seedance 2.0-2.5 / Kling 3.0 | T2V/I2V，做开场钩子、转场 |
| 二次元/国漫**漫剧** | 可灵 AI（快手）+ 角色锁定；星宇智算（B端） | 中文提示词、9:16 竖屏原生 |
| 批量**短剧流水线** | 即梦AI（剧本→分镜→合成黑箱）/ 万兴剧厂 | 一个人手机出一条像样片段 |
| 教学课件**轮播/B-roll** | course.html 截图 + ffmpeg drawtext 弹字（本地零成本） | 见 ep8k_build 管线 |

**核心判断**：教育内容 8 成「过程/逻辑动画」用 Manim/课程页就够（可控、免费、快），写实镜头才花 API 钱上 Veo/Seedance。别把所有镜头都喂 T2V——又贵又不稳定、角色易变脸。

## 一、2026 T2V 大模型榜（Artificial Analysis 盲测 Elo，选镜头用）
**综合/榜首梯队（要出写实镜头查这页）**：
- Google **Veo 3.1**＝综合第一（提示词遵循/原生音频/写实）
- 字节 **Seedance 2.0→2.5**＝原生 ~30s、~50 参考帧、4K 路径，多镜头最强（Elo ~1225）
- Google **Gemini Omni Flash**＝多轮编辑+世界知识（Elo ~1240，T2V带音频榜首）
- 快手 **Kling 3.0/Omni**＝导演级运镜控制（Elo ~1110）
- 阿里 **HappyHorse 1.1**＝企业 API（Elo ~1149）
**国产口播/漫剧**：可灵（角色锁定+视频续写，运镜丰富）、即梦AI（端到端黑箱）、腾讯智影/黑狐/讯飞智作（数字人）。
**用前必做**：去 artificialanalysis.ai/video/leaderboard 看实时榜（榜单每月变，别拿旧排名下单）。

## 二、教育视频生产流水线（李彦明线，已跑通）
> 7 专家流水线技能 = teacher-video-lesson-team；本技能补「画面/配音选型」层。
1. 定题→教学设计→脚本（前30s钩子，不上自我介绍）
2. 画面三路并行选：
   - 逻辑/公式/代码动画＝Manim（本地，720p，Base.setup 里加水印铁律）
   - 课件轮播＝course.html 截图 或 ffmpeg drawtext 弹字（零成本）
   - 写实开场/B-roll＝Veo 3.1 / Seedance（花钱，只做点睛镜头）
3. 配音：TTS（edge 中文 zh-CN-YunxiNeural 最稳，**千万别用英文语音念中文**——每段会截断到 3-4 秒）；冲质感换 openai/elevenlabs 或真人自录
4. 合成：ffmpeg 定帧补齐(tpad)+concat+硬字幕 SRT+drawtext 水印双保险；中文路径复制 ASCII 名再烧
5. 抽帧 vision_analyze 终验四项（字幕/水印/无豆腐块/底色）

## 三、踩坑速记（血泪）
- **edge TTS 语音**：config 默认 en-US-AriaNeural（英文）→ 念中文只出 3 秒。改用 zh-CN-YunxiNeural/zh-CN-YunyangNeural（edge-tts 包直接调用，rate 可调 -5%）。
- **Manim 动画时长 < 配音**：尾帧 tpad clone 会「卡住像坏了」；解法＝主片统一课程页弹字风格，动画只放进 12s 拆条短视频（时长刚好）。
- **filtergraph 里 `C:/` 冒号炸 parse**：fontfile 用相对名（msyh.ttc 放 cwd），本地字体避开绝对路径。
- **T2V 角色一致性**：跨镜头变脸是漫剧最大坑，必须用角色锁定（可灵/星宇智算），别裸调 Veo 串多镜头。
- **中文路径烧字幕**：先复制到 ASCII 临时目录，再 ffmpeg 烧，否则乱码。

## 四、交付铁律（继承 teacher-video-lesson-team）
- 所有视频成品右下角白色 ~40% 透明静态水印「李彦明 15684394135」（Manim 在 Base.setup，ffmpeg 层 drawtext 双保险）。
- 传统文化系列配色 C 玄金红（色板见该技能）。
- 单文件/可离线优先；B-roll 与课件零外链。

## 何时用
- 做任何教育/知识/口播/短剧视频前 30 秒查「决策树」选工具组合
- 决定某镜头用 Manim 还是 T2V 还是数字人时查「一」
- 配音截断/角色变脸/水印丢失/字幕乱码 时查「三」踩坑
