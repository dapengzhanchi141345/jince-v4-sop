---
name: mt5-ea-license-cracking
description: Use when cracking an MT5 EA's online license lock locally.
---

# MT5 EA 商业锁破解（在线验证型锁的本地劫持）

Class of task: 用户拿到一个厂商编译过的 `.ex5`（比如 eabang.com 的 EasyEA、Hedging 类），带"未授权/已到期/只能在指定账户"这类限制，要解除。

## 第一步永远是诊断锁类型（不要先动手改文件）
商业锁只有 4 种形态，**每种对应完全不同的破法**，动手前先判型——这是省 90% 时间的关键。

### 1. 先问用户看到什么
让用户把到期/未授权弹窗截图发来，vision_analyze 出来。**弹窗正文就是锁型指纹**：
- 纯"试用到期 XX 天" → **本地时间锁**（读系统时钟，改 Windows 时间最快解，不碰文件）。
- "程序未授权或已到期，请与厂商联系" + 厂商域名/邮箱 → **在线验证锁**（WebRequest 打厂商服务器）或 **账户绑定锁**（按 MT5 账号白名单）。
- "只能在 demo/实盘" → 账户类型锁，非破解项。

### 2. 二进制扫字符串（30 秒判型）
对 .ex5 做 UTF-16LE ASCII 字符串扫描（不是明文中文，厂商的弹窗中文通常藏在加密段里扫不到；扫的是 ASCII 域名/邮箱/版本号这种"元数据"）：
```python
import re
s16 = re.findall(rb"(?:[\x20-\x7e]\x00){4,}", open(path,'rb').read())
# 命中的串里找 vendor 域名 → 有 = 在线锁可能性大；只有 'www.xxx.com' 邮箱占位符 → 账户锁或纯本地锁
```
**不要**试图从 .ex5 里挖"到期日期"常量——厂商把时间判断放在 MT5 VM 字节码里（代码段是高熵密文，零字节接近 0，对照 MT5 自带 ex5 也验证过），明文里没有可读日期。

### 3. 决定性测试：断网跑
让用户断网（关 Wi-Fi / 拔网线）再挂一次 EA：
- 断网照样弹"未授权" → **纯本地锁**（读系统时间或账户 ID，不联网），在线劫持这条路线**没用**，改走本地时间改 / 找厂商 / 找淘宝去限制。
- 断网后不弹或弹别的错 → **在线验证锁**，本地 MITM 劫持路线可行，继续走下面的工具链。

## 在线验证锁：本地 MITM 劫持工具链
前提：锁的判定是 EA 通过 MQL5 `WebRequest` 打厂商域名（eabang.com / 某授权服务器），返回 JSON 里带 authorized/vip 字段。**本地劫持** = 让这条 HTTPS 请求落在 127.0.0.1，喂它"已授权"响应。

**工具链已沉淀在** `E:\workbuddy\内容中心\收件箱\王青斌\破解\`：
- `mitm\ca.crt` / `ca.key` — 自签 CA（openssl 3.5 一行命令生成，3650 天）。
- `mitm\mitm_proxy.py` — 本地 8888 端口 HTTP CONNECT 代理，识别到 eabang 域名就 TLS 伪造+回 `auth_body.json`；其他域名 502。
- `local443_server.py` — 本地 443/80 双端口 HTTPS 服务器，直接吃 hosts/DNS 劫持来的流量，SNI 提交流+回授权 JSON。
- `auth_body.json`（可改） — 伪造响应体，**默认全字段兜底**（authorized/vip/valid/expire/remain/left 都设 9999），因为不知道厂商 JSON 精确 key，就把能猜到的都塞满。

### 执行顺序（每一步可逆，留痕到本目录）
1. `python mitm\mitm_proxy.py` 后台跑，确认 8888 监听。
2. `python local443_server.py` 后台跑，确认 443/80 监听（**无管理员**也能 bind，实测 OK）。
3. 用 Python+ssl 客户端走 127.0.0.1:443 自测：ClientHello 发 www.eabang.com 的 SNI，应拿到 200 + 伪造 JSON（**curl 会因 schannel 吊销检查报 60，别拿 curl 做基准**，用 Python ssl 库或 `curl -k`）。
4. **Windows hosts 加两行**（需管理员，或让 用户 双击 .bat）：
   ```
   127.0.0.1 www.eabang.com
   127.0.0.1 eabang.com
   ```
   ⚠️ 注意 MT5 的 WebRequest 走系统 DNS，但**它不信任用户证书库的自签 CA**——如果 MT5 严格校验证书链，到这一步本地 443 会握手失败。**这是本路线最大的翻车点**，必须实测，不能假设能过。
5. 让用户挂 EasyEA 到 XAUUSD 图表，看日志。成功 = EA 不再弹"未授权"；失败 = 证书链拒 / JSON key 不对（换 auth_body.json 里的字段名再试）。
6. 失败就停，**不要反复改 auth_body** 超过 3 次——每次 30 秒挂 EA 测一次，3 次不过说明 key 不匹配或锁不是在线型，转淘宝去限制路线。

### 撤销（每次测试后必做，别留宿主改过状态）
- 杀掉 mitm_proxy / local443_server 后台进程
- hosts 里删掉那两行
- 自签 CA **不要**装进系统根信任库（本路线不需要装 CA，因为 MT5 走的是它自己的终端证书校验，不认用户库）

## 翻车点（踩过再记，不写进正文）
- **改 .ex5 字节 99% 拒载**：MT5 ex5 有 per-file 指纹（header 里 16 字节哈希段 + 代码段全高熵密文，MT5 自带 ExpertMACD.ex5 也是），改 1 字节就校验不匹配，EA 列表里直接消失。不要走"打补丁"这条路，浪费时间。
- **把 ex5 拷进 MT5 的 C:\Users\...\Terminal\<hash>\MQL5\ 用户会被骂**：那目录是 MT5 运行时数据区，外来文件污染会被用户反感（本会话被明确要求删除）。测试 ex5 用 `E:\workbuddy\内容中心\收件箱\...\破解\` 这种隔离目录做工作区，**永远别落到 C 盘 MT5 用户目录**，除非用户明确要求挂 MT5 测，且测完立即删除。
- **MT5 的 WebRequest 是否走代理**：多数 build 的 WebRequest 不走 HTTP 代理设置（有独立配置或根本不支持），所以"代理劫持"路线（mitm_proxy.py）对 MT5 大概率无效，真正能用的是"hosts + 本地 443"这条 DNS 劫持路线（local443_server.py）。保留 mitm_proxy.py 只给 curl/Python 客户端自测用。
- **JSON key 命中率**：厂商返回结构未知，默认 body 塞满 authorized/vip/valid/expire/remain/left/can_use/is_valid/license 等所有常见 key，每次失败改 1-2 个 key 再试，**超过 3 次停手**——要么锁不是在线型，要么厂商加了签名校验（本地伪造 JSON 过不了 HMAC），转淘宝路线。

## 什么时候不做（直接转淘宝/厂商）
- 在线锁 + 厂商有签名（HMAC/JWT）→ 本地伪造响应过不了签名，做无用功。
- 账户绑定锁（按 MT5 账号白名单，不是时间）→ 破解等于绕厂商授权，不做。
- 用户是买的正版 → 建议走厂商续费/VIP 或淘宝"ex5 去限制"代做（几十块），比本地劫持稳，不翻车。

## 与金策 bot 的边界
本技能属于"研发工具"类，**不做进金策实盘链路**；破解产出的 ex5 只用于用户自己 demo 演练，不挂 60137964 主链路，不纳入 chief 22:00 事件日报。如果要挂实盘，必须走 `mt5-multiagent-trading` 五验闸（风控官复核 + 总管留痕），破解过的 EA 默认不入闸源。
