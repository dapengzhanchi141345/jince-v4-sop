---
name: hermes-voice-media
description: Use when 给 Hermes 加语音对话/语音转写/摄像头"我看你"交互媒体。速装+验货。
---

# Hermes 语音 & 交互媒体（STT/TTS/摄像头/Discord 语音房）

李彦明线：把"我说你听、你跟我读、我还能看你画面"搭起来。配置层在 Hermes（`stt:`/`tts:`/`voice:` 段，见 hermes-agent 技能），本技能给"动手+验货"层，避开本机（hf.co 被墙、venv 无 pip、外网断）三个坑。

## 能力边界（先说清，别画饼）
- Hermes **原生**只有 Voice Mode（实时语音：CLI 录音 / 平台自动语音回 / Discord 语音房）+ Vision（看图）。
- **没有"摄像头对摄像头毫秒级双向视频通话"**。能做的"视频聊天"= ①回合制"我看你画面+我语音回"（抓帧→识别→回话，循环）②Discord 实时**纯语音**房。要真双向视频走会议软件。

## 1) STT 语音转写（本地离线，免费）
判据先看 config：`stt.enabled:true` + `stt.provider:local` + `stt.local.model:base` 基本默认就在，**缺的是模型文件**。
- 模型源 hf.co 在本机被墙（`curl -m8 https://huggingface.co` 返回 000），但 `https://hf-mirror.com` 通。预下载：
  ```python
  import os; os.environ["HF_ENDPOINT"]="https://hf-mirror.com"
  from huggingface_hub import snapshot_download
  snapshot_download("SYSTRAN/faster-whisper-base", allow_patterns=["model.bin","*.json","*.txt"])
  ```
- 之后离线跑：`HF_ENDPOINT=https://hf-mirror.com HF_HUB_OFFLINE=1` 下 `WhisperModel("base", device="cpu", compute_type="int8")`，转写前把音频转 16k mono wav（ffmpeg `-ar 16000 -ac 1`）。
- **验货不凭"下载成功"**：拿一段清晰中文音实测转写，读结果确认够不够用（base 档偶尔把个别字转成繁体/同音字，不影响理解；要更准再拉 small 档，需再下一个模型）。

## 2) TTS 中文回话
- config 里 `tts.edge.voice` 默认常是英文（`en-US-*`）→ 念中文会截断。改：`hermes config set tts.edge.voice zh-CN-YunxiNeural`（官方 CLI，别手改 YAML）。备选 `zh-CN-XiaoxiaoNeural`（女声）/`zh-CN-YunyangNeural`（新闻男声）。
- 不依赖 Hermes 管线、要精确控制时用 `edge-tts` Python 包直调：`Communicate(text, "zh-CN-YunxiNeural", rate="-5%")`。

## 3) 摄像头"我看你"回合制（本机 ffmpeg dshow）
- 设备**自动探测**（不写死设备名，符合局域网 IP 同款铁律）：`ffmpeg -sources dshow` 解析第一个 video / audio 设备名（形如 `USB2.0 HD UVC WebCam`）。
- 抓帧：`ffmpeg -f dshow -i video="<dev>" -frames:v 1 -update 1 out.jpg`；录音：`ffmpeg -f dshow -i audio="<dev>" -t N -ar 16000 -ac 1 mic.wav`。
- 闭环：抓帧+录音 → `vision_analyze` 读帧（看懂画面）+ faster-whisper 转写 mic.wav（听懂你）→ TTS 回话。成品脚本 `E:\workbuddy\内容中心\视频聊天\video_chat_capture.py`（写死 ffmpeg 绝对路径、GBK 安全、找不到设备明确报"跳过"不崩）。

## 4) 实时语音房（Discord，近实时纯语音）
- 依赖 `discord.py[voice]`（自动带 PyNaCl 加密 + opus 编解码）。只给 token 前先把依赖装好。
- 装完让用户去 discord.com/developers 建 Bot、拿 token、进服拉进某语音频道；缺 token 就停在"框架就绪"，不硬凑。

## 踩坑（本机血泪，逐条带机制）
- **venv 无 pip、ensurepip 也炸**：本机 Hermes venv 装不了 pip。改用 uv 直装到该解释器：`uv pip install --python "<venv>/Scripts/python.exe" "discord.py[voice]"`（先 `uv --version` 确认 uv 在，否则走系统 python3 -m ensurepip 再装）。别在"装不上依赖"上耗——是安装器缺，不是包不存在。
- **改平台适配器要保留 `**kwargs`**：基类 `BasePlatformAdapter.send_voice/send_video/send_document` 调用时会传额外 kwarg（如 `is_voice=`）；某适配器（如 weixin）重写这些方法时签名**必须带 `**kwargs`**，否则运行时 `TypeError: got an unexpected keyword argument 'is_voice'` 导致"我发的语音在微信发不出去"。改这类签名前 `grep -nE "async def send_" <adapter>` 把该适配器所有发媒体方法一次对齐；改完 `py_compile` 验证，且要**网关重启**才生效（源码改动不进热更）。
- **外网断 ≠ 全断**：本机 hf.co/github 443 常墙，但 `hf-mirror.com` 通、`gh` 自带解析器 REST 通。下模型走镜像、验远端 commit 走 `gh api`，别直接 `curl hf.co` 判死。
- **改 Hermes 源码/ config 前先备份**（`.bak-<tag>`），config 用 `hermes config set` 官方 CLI 改（手改 YAML 易缩进炸掉 live gateway）。

## 验货铁律
- 每个环节都要真跑一遍再报"通了"：STT 用清晰音实测转写、摄像头真抓一帧读图、语音回话实发。子代理/工具自报"已装"不算数，盘上实测为准。
