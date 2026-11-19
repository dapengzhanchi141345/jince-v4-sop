# iLink 微信通道：重连 / 开通 / 验证

用户说「开通微信 / 微信收不到消息 / 很久没用要重开」时的专用流程。适用前提：本机 Hermes 网关跑 iLink weixin 平台（账号文件 `weixin/accounts/` 存在）。

## 决策链（30 秒定级）
通道轮询活吗？→ 凭证还有效吗？→ bot 能先开口吗？→ 否则 QR 重登。

## 1. 通道状态（日志是唯一事实源）
- `gateway_state.json` 的 platforms.weixin.state 可能是僵尸值，只看 `tail -c 60000 logs/gateway.log | grep -i weixin` 尾部：
  - 尾部无 weixin `poll error` → 通道活着（轮询成功静默，只记错误与 inbound）。
  - 尾部有 `poll error (N/3): ... getaddrinfo` → 换网/DNS 后轮询断；N<3 会自愈，满 3 且无后续 `Connected` 行 → 按 SKILL.md 步骤 4 走重启（会话内重启做不到，给 bat）。
  - 有 `inbound message: platform=weixin` → 收消息已通。

## 2. 凭证直探（不重启、不扫码的快检）
- 账号文件在 `weixin/accounts/<id>@im.bot.json`（token、base_url、user_id）；`.sync.json` = get_updates_buf；`.context-tokens.json` = 每 peer 的 context token；`.env` 有 WEIXIN_ACCOUNT_ID / WEIXIN_TOKEN / WEIXIN_BASE_URL。
- 直探：POST `https://ilinkai.weixin.qq.com/ilink/bot/getupdates`，body `{"get_updates_buf": "<sync.json 里的值>"}`，headers：`Authorization: Bearer <token>`、`AuthorizationType: ilink_bot_token`、随机 base64 `uin` 头。HTTP 200 = 凭证活着（msgs 为空正常）；401 / 会话类 ret = 要重登。
- 不要写 getupdates 轮询循环侧查——buf 游标与网关轮询循环共享，侧轮会抢走更新；验证 inbound 只看 gateway.log 行。

## 3. session-not-ready（久不通后最典型的卡点）
- iLink 规则：**bot 不能先开口**。久不通后主动 sendmessage 一律回 `{"ret":-2,"errmsg":"prepare failed"}`（带不带 context_token 都一样）。这是 session-not-ready，**确定性、不是限流**——不要重试、不要退避、不要归因「平台故障」。
- 唤醒：让用户在微信给 iLink bot 发任意一条消息（如「1」）→ 网关收 `inbound message: platform=weixin` → context token 刷新 → 双向全通。这是落到用户手上的一步，必须给零歧义指令（哪个 bot、发什么）。
- 等待期间后台监测：`timeout 2700 tail -n0 -F logs/gateway.log | grep --line-buffered 'inbound message: platform=weixin'`，匹配即主动报全通，不静默。
- ret=-14（session expired）：丢 context_token 重试一次；仍 -2/-14 则同样走唤醒或 QR 重登。

## 4. QR 重登（唤醒失败 / 凭证彻底失效的终局手段）
- 端点：GET `ilink/bot/get_bot_qrcode?bot_type=<n>` → 轮询 GET `ilink/bot/get_qrcode_status`（成功返回新 token/base_url/user_id，写回账号文件 + .env，重启网关生效）。
- 二维码约 2 分钟过期：**取码→渲染 PNG→交给用户必须一枪打完**（一键脚本：取码、出图、自动打开、轮询+自动刷新），逐步操作必过期。

## 铁律
- 本账号只稳定收**私聊**，群聊收不到——别拿群测试。
- 向用户汇报三档定级，大白话：「通道已连 / 需要你给微信 bot 发一条消息 / 要扫一次码」，不念 ret 码和黑话。
