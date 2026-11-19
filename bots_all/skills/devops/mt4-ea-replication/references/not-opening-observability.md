# EA “挂上不开单” 可观测性根治 + 加载确认

客户报“EA 挂了不动/不开单”时的两层定位法与交付规范。对应 SKILL.md “EA 不运行 根因定位 SOP” 的 step 0 与 step 4。

## When to Use
客户/自己反馈“EA 挂上了但不开单/不动/挂了没反应”, 且编译 0 错、.ex5 已就位——需要判断是「没真加载」还是「能跑但静默不开单」, 并把“为什么不开单”变成可自查的交付。

## A. 先确认 EA 真加载了(读 UTF-16 终端日志)
`.ex5` 在 `MQL5\Experts\` ≠ 已挂载。终端日志才是铁证:
- 位置: `C:\Users\ASUS\AppData\Roaming\MetaQuotes\Terminal\<hash>\logs\YYYYMMDD.log`
- 编码: **UTF-16LE**, 直接读会满屏 `\u0000` 乱码。读法: `iconv -f UTF-16LE -t UTF-8 <log>` 或 python `open(f,'rb').read().decode('utf-16-le',errors='ignore')`。
- 关键行(任一缺失=没真正加载):
  1. `expert <EA名> (<品种>,<周期>) loaded successfully` — 终端挂上了
  2. 你 OnInit 里自定义的 `Print("<前缀> attached: ...")` — EA 逻辑真跑了
  3. `automated trading is enabled/disabled` — 算法交易总闸状态
- **本机多个终端 datafolder(7643C0B9…/A3B1DF…/1B13…/917A…)**, 拷错目录就永远加载不到。先确认客户挂的是哪个终端再放。
- 够不到客户机时: 本地同类终端日志 + 代码静默分支审计就是检查面(用户会说“你自己系统检查”)。

## B. 能编译但永不开单 = 头号根因“零可观测性”
每个 gate 静默 `return`, 客户只有 OnInit 那句 attached, 只能报“挂了不动”。根治=交付时做**可观测版**:
1. **限频诊断日志**: 每个 gate return 分支调一个 `Diag(string why)`, 内部 `g_blockReason=why` + 60s 节流(换原因才打, 防每 tick 刷屏)。
2. **面板最后一行 = 当前阻塞原因**: `Comment()` 里拼一行 `"当前未开单: " + g_blockReason`(开单时清空)。
3. **逃生 input(2-3 个可配开关)**, 让客户/自己能临时验证信号本身:
   - `InpAllHours`(bool, 好时段放宽到全天, 只封拉黑小时)
   - `InpLooseSignal`(bool, 信号放宽)
   - `InpServerOffsetH`(int, 服务器→目标时区偏移, 别硬编码 +5h)
   排查顺序: 开 AllHours/关 UseSession 看信号能否开单 → 能开=时段门太窄; 仍不开=信号/时区问题, 调 offset 或放信号。

## C. 面板能开的写法(MQL5, 本机 build)
- `Comment(string)` 每 tick 覆盖同一块, 用 `StringFormat` 拼多行(`\n` 分行)。面板崩了不影响交易(展示层解耦)。
- 想固定定位用 `OBJ_LABEL`:`ObjectCreate(0,name,OBJ_LABEL,0,0)` **5 参**(x/y 走 OBJPROP_XDISTANCE/YDISTANCE, 不是第 4/5 参), `color` 类型名不是 `clr`。详见 `mt5-indicator-authoring` §8a。

## D. 交付话术
说明.txt 加“挂上不开单·按顺序自查”一节: ①先确认 attached 行+面板出现(没=没刷新/没开算法交易) ②看面板最后一行原因对号入座 ③时区对不对 ④面板日志都不出=没真跑(确认 ex5 在**这个终端**的 Experts + 终端重新加载)。让客户只需“把面板截图/日志发我”即可定位, 不盲猜。
