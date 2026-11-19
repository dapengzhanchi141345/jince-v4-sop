# MT5 attach 探针的 python venv 选型（实跑验过）

只读探针（读 account/positions/orders，attach 不 spawn）选哪个 python 跑：
- hermes 自带 python（E:\workbuddy\国外模型\hermes\tools\python-3.14.*）没有 MetaTrader5 模块——用它跑 attach 探针首跑 import 即失败，别用。
- 有 MetaTrader5 的可用 venv：
  1. ATE 环境 `C:\Users\ASUS\.workbuddy\binaries\python\envs\ate\Scripts\python.exe`（引擎链主环境；起子代时盖 OMP_NUM_THREADS=2 / OPENBLAS_NUM_THREADS=2，防 16GB 机器内存吃紧 fork 崩）；
  2. jince_bot venv `E:\workbuddy\内容中心\交付\AI交易bot方案_20261019\jince_bot\.venv\Scripts\python.exe`（MetaTrader5+pyzmq 在位，只读探针直接可跑，本会话实测读到 60137964 账户实数）。
 3. 引擎直跑解释器 `D:\workbuddy\binaries\python\versions\3.13.12\python.exe`（live24/jince_live24.py 实跑所用，Get-CimInstance 命令行确认；带 MetaTrader5 模块，只读探针可直接用它，模块名仍 `import MetaTrader5`；改引擎代码后用同一解释器即跑新码，与引擎环境同源零偏差）。
- 模板：`mt5.initialize(path=r"C:\Program Files\TMGM MT5 Terminal\terminal64.exe")` attach 运行中的引擎终端 → 读 account_info/positions_get/orders_get → 立即 `mt5.shutdown()`。永不 spawn/kill terminal64（IPC 崩链铁律）。
- **import 名铁律：`import MetaTrader5 as mt5`，不是 `import mt5`**——site-packages 里的包名就叫 MetaTrader5，裸写 `import mt5` 必 ModuleNotFoundError（引擎代码一律 `import MetaTrader5 as mt5` 别名；自写探针/起子代必须同款，连烧两拍探针的实踩坑）。选 venv 前先 `ls <venv>/Lib/site-packages/ | grep -i metatrader` 核包名与在位，再定解释器。
- **别猜引擎链用哪个 venv**：以 JinCeAutoCycle 任务 Actions 里的解释器路径为准（任务实跑配置 > 目录惯例）；`E:\GoldstrategyEngine\python\envs\ate` 与 `C:\Users\ASUS\.workbuddy\binaries\python\envs\ate` 是两个不同的 ATE 环境，模块不共享，各查各的 site-packages。
