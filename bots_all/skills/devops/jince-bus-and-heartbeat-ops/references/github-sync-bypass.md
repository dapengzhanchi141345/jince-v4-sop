# GitHub 推 443 墙绕行（jince_github_sync.push_via_api）

## 何时用
- 本机任何"上传代码到 GitHub / 全量同步仓库"需求：直连 `git push`（https）被 443 墙 reset（`Recv failure: Connection was reset`），不可用。
- 固定绕行 = `E:/workbuddy/国外模型/hermes/scripts/jince_github_sync.py` 的 `push_via_api(dirpath, repo, branch, tag, excludes=())`：
  - gh CLI 走 api.github.com 绕 443 墙（gh 全路径解析, 认证仍需 token）
  - Git Data API 全树推：内容 sha256 去重 + 本地 blob 缓存（只传变更文件）→ 自底向上建嵌套树 → commit → 更新 ref（非 force）
  - 空仓（Git Data 全 409）唯一解锁 = Contents API 造首笔提交
  - 调用范式：`from jince_github_sync import push_via_api; changed, err = push_via_api('E:/GoldstrategyEngine', 'GoldstrategyEngine', 'main', 'SD批xxx', excludes=('.git','data','allsyms_m15','allsyms_m15_ev','.venv','scratch_bus'))`
- 夜间全推 cron（默认 disabled, 手动跑/按需开）：`金策·GitHub 夜间全推`（03:00, jince_github_sync.py all = SaaS 全量+工作台账）、`技能·GitHub 夜间全推`（04:30, skills_github_sync.py 复用 push_via_api 推 default profile 技能）。

## 坑
- **并发竞态（11-15 实踩, 已修）**: push_via_api 的 ThreadPoolExecutor(max_workers=8) 里 `up()` 写共享 cache dict 与 `work()` 的 `json.dump(cache)` 迭代并发 → `RuntimeError: dictionary changed size during iteration`, 整次推送 exit 1。修 = `cache_lk` threading.Lock 罩住 up() 的 cache 写入 + 所有 json.dump(cache) 点。**再遇 'dictionary changed' 先查锁点是否在后续合并中丢失, 不是 gh API 的问题。**
- 宣称推送成功前必须读 GitHub HEAD 验证（`gh api repos/<owner>/<repo>/commits?per_page=1` 看 commit 时间戳）——API 读是唯一可信 handle, 脚本 print 的 changed 计数不算。
- excludes 必须排除大数据目录（allsyms_m15/*.npz、data、.venv、scratch_bus）, 否则 blob 量爆炸, 全树推跑数小时。
- 推送范围含 research/ 全量脚本+参数表+御审裁定文档 = 版本锚点（"深度优化完传 GitHub" 李令的落地形态：commit 全量→push_via_api→HEAD 验讫→再报"已上传"）。
