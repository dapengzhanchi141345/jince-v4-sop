---
name: hermes-voice-video
description: 配置/排障 Hermes 语音(STT+TTS)与摄像头视频输入；本地 Whisper 离线转写+中文TTS。
---

# Hermes 语音 / 视频输入 配置与排障

用户要"语音对话""视频聊天""发语音你给我听/回"时，先按本技能搭闭环。Hermes 原生有实时**语音**（Voice Mode：CLI 按 Ctrl+B 录音 / Telegram·Discord 自动转写+语音回 / Discord 语音房），但**没有摄像头对摄像头那种实时视频通话**——视频只能走"回合制抓帧"。别把后者当原生功能承诺。

## 〇、先判环境（30 秒，别盲装）
| 检查 | 命令 | 说明 |
|---|---|---|
| faster-whisper 装没 | `venv python -c "import faster_whisper"` | Hermes venv 里查，别查系统 python |
| 外网/HF 通没 | `curl -m6 https://huggingface.co -o /dev/null -w "%{http_code}"` + 测 `https://hf-mirror.com` | HF.co 常被墙；镜像通常通 |
| 摄像头/麦克风在不在 | `ffmpeg -sources dshow 2>&1 \| grep -iE "video\|audio"` | 拿到确切设备名 |
| 现成 STT/TTS 配置 | 读 config.yaml `stt:` / `tts:` 段 | 本机常已 `stt.enabled:true`，缺的是模型/中文 voice |

**关键认知**：本机 Hermes 的 config 通常已经写好 `stt.enabled:true` + `tts` 各 provider。真正的拦路虎只有两个——① 本地 Whisper 模型没下载且 HF 被墙；② edge TTS voice 被设成英文念中文。都一改就好，不用从零装。

## 一、STT（听你说话）启用+验货
1. **模型下载（走镜像，一次性）**：HF.co 000/被墙时用 hf-mirror。模型名必须跟 config `stt.local.model` 一致（默认 `base`）：
   ```
   set HF_ENDPOINT=https://hf-mirror.com
   <hermes venv python> - <<'PY'
   import os; os.environ["HF_ENDPOINT"]="https://hf-mirror.com"
   from huggingface_hub import snapshot_download
   print(snapshot_download("SYSTRAN/faster-whisper-base", allow_patterns=["*.bin","*.json","*.txt","*config*"]))
   PY
   ```
   （hermes 主套 venv python 路径形如 `E:/workbuddy/国外模型/hermes/hermes-agent/venv/Scripts/python.exe`，按本机实际定位。）
2. **离线验（证明真能跑，别信"下载成功"）**：设 `HF_HUB_OFFLINE=1` 强制走本地缓存，加载 `WhisperModel(model, device="cpu", compute_type="int8")` 转写一段已知文本的音频。
3. **验货要干净样本**：用 edge-tts 现生成一句清晰中文（如 `zh-CN-XiaoxiaoNeural`）→ ffmpeg 转 16k 单声道 wav → 喂 Whisper。**别拿之前那串合成/嘈杂 mp3 直接测**——base+int8 对合成音转成繁体/同音字是正常的（够理解就行），对清晰人声才准。精度不够就升 `small` 档（再下一个模型，~10min）。

## 二、TTS（我中文回话）
用官方 CLI 改，**不手改 YAML**（防破坏 live gateway，且 config 是活文件）：
```
<hermes exe> config set tts.edge.voice zh-CN-YunxiNeural
```
改前先 `cp config.yaml config.yaml.bak-voice` 备份。edge 免 key 最省事；要更自然可换 `openai`/`elevenlabs`（需 key，见 config `tts:` 段）。`stt` 侧同理，本地档免 key 优先。

## 三、"视频聊天"= 回合制抓帧闭环（非实时视频流）
Hermes 没双向实时视频。能搭的是：**抓一帧你的摄像头/屏 → 我用视觉读 → 我语音回**，循环着来。
- 抓帧：`ffmpeg -f dshow -i video="<确切设备名>" -frames:v 1 out.jpg`（设备名先用 `-sources dshow` 拿，别写死）。
- 读帧：`vision_analyze` 把 jpg 喂进去问问题。
- 回话：TTS 中文朗读（第二节）。
- 桌面版/实时语音房要另说：Hermes Desktop 有 voice，Discord 语音房可多人实时边说边聊——真想要毫秒级就指这条，别硬做"摄像头对摄像头"。
- 与 `webrtc-remote-view`（远程看另一台设备摄像头/屏）分工：那个是"看别人机器的画面"，本技能是"本机语音/视频输入给 Hermes"。不重叠。

## 四、踩坑速记
- **HF.co 被墙**：`curl https://huggingface.co` 000，但 `hf-mirror.com` 200。所有 HF 模型下载/加载都要 `HF_ENDPOINT=https://hf-mirror.com`；验离线加 `HF_HUB_OFFLINE=1`。
- **Windows 无 symlink**：HF 缓存会警告降级（仍可用，多占盘），可 `HF_HUB_DISABLE_SYMLINKS_WARNING=1` 静音，非阻塞。
- **模型名 vs config 不一致**：WhisperModel("small") 但 config `stt.local.model:base` 时，STT 实际用 base——升级要**同时**改 config + 下对应模型，否则白下。
- **合成音验 STT 会误判**：base+int8 转合成 TTS 输出繁体/同音字是正常（够理解），别当"坏了"；验清晰度用真人/干净样本。
- **ffmpeg 路径含版本串**：WinGet 装的 ffmpeg 全路径带版本号（`.../ffmpeg-8.1.1-full_build/bin/ffmpeg`），别写死短路径，用 `where ffmpeg` 或全路径。
- **config 是活文件**：改 `stt`/`tts` 只走 `hermes config set`，改完 live gateway 下次触发即生效（profile 懒启动），别手改 YAML 缩进。
