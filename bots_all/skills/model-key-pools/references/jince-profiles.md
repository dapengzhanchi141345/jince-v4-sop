# 金策 per-profile key allocation (profiles/<name> layout)

Topology: 4 gold-strategy bot profiles — `default` (root `$HERMES_HOME`), `chief`, `risk-officer`, `strategy-rd` (each under `profiles/<name>/`). Each profile's `config.yaml` has a `model:` section (main provider, .cn endpoint) + `providers:` (per-role blocks incl. legacy .com fallback) + `fallback_providers:` list. `.env` holds the key slots (`AGNES_KEY_<ROLE>_COM` etc.) — **30+ profiles exist** (金策 4 + post-mortem + 26 教学/专家岗), all under `profiles/`.

## Live topology facts (verify before assuming)
- **One root gateway process serves ALL profiles**: every `profiles/*/gateway.lock` and root `gateway.lock` carries the SAME pid. Profile config changes need NO per-profile gateway kill — they load on that profile's next session/cron fire. A full immediate cutover = the 一键重启网关.bat (user side).
- **Shared round-rotator key families (K10-style) live ONLY as inline `api_key:` blocks**, one set duplicated into every profile's `providers:` map, assigned main/fallback per profile in rotating triplets. They are invisible to `.env` sweeps — sweep config for them when counting the fleet (SKILL.md step 1).
- Per-role dedicated blocks (`agnes-<role>`, `agnes-bot-<role>`) point at `.env` slots; some legacy blocks mis-aim `base_url` at the 8787 pool proxy — a key routed through the pool proxy gets ROTATED AWAY from that key (the proxy ignores its api_key), so dedicated blocks must point at the key's own endpoint (.cn/.com direct).
- 池 json `agnes_pool_keys.json` is `{endpoint, keys}` — read `.get("keys")`, never iterate the dict itself.
- 429-wall state of keys drifts day to day (free-tier daily quota): always re-probe before any allocation decision, and route rechecks through the 00:05 sentinel rather than ad-hoc probes.

## Recipe (allocate N new .com keys, one per role)
1. **Verify first (先验后配)**: fire a minimal `chat/completions` ping at the candidate endpoint(s). 200 + real completion + `/models` listing = live. Record which endpoint(s) each key actually lives on — a key 401 on `.cn` can be fully live on `.com`.
2. **Backup**: `cp .env .env.bak-<ts>` + `cp config.yaml config.yaml.bak-<ts>` per profile before writing.
3. **`.env` slot OR inline key (pick per source)**: user-supplied keys usually go INLINE in the provider block (`api_key: sk-…` — that's how the live 金策 blocks are written; `key_env:` still listed for display). Only use `.env` + `key_env` when the profile already has that slot convention. Never print full keys to chat/logs — mask on display.
4. **Provider block**: insert N new pools into the `providers:` section of that profile's `config.yaml` — ONE block PER KEY (e.g. `agnes-new-1..4`), each with `api/base_url` = the key's own endpoint + `api_key:` + full model surface:
   ```yaml
   agnes-new-1:
     name: agnes-new-1
     api: https://apihub.agnes-ai.com/v1
     base_url: https://apihub.agnes-ai.com/v1
     api_key: sk-…(full)
     key_env: AGNES_NEW_1_API_KEY
     discover_models: false
     context_length: 512000
     models:
       agnes-3.0-flash: {}
       …(same surface as sibling blocks)
   ```
   Locate the next top-level key line after the last existing provider block (`\nfallback_providers:` / `\ntoolsets:`) and insert BEFORE it — a plain EOF append lands the block under the wrong top-level parent and provider discovery silently skips it.
5. **Fallback wiring**: append one `- provider: <new-pool>` + `model:` entry PER NEW KEY at the END of the `fallback_providers:` list (main chain stays primary; new keys only fire on upstream 429/5xx exhaustion).
6. **Scope exactly as ordered**: the user says which profiles get the keys (e.g. 金策 3 岗, 运营岗不配) — inject only those `profiles/<name>/config.yaml`; a key pool is per-profile, un-allocated profiles simply don't see the new pools. Same vendor different account = separate key set: probe each distinct base_url + chat ping before reusing any key→pool mapping.
7. **Verify**: each new pool block offset < next top-level key offset; fallback entries appended inside the `fallback_providers:` list only; main `model.provider` still points at the original .cn block (insert-only, main chain untouched).
8. **Restart / reload**: profile gateways auto-respawn via the `Hermes_Gateway` Windows task (its `Hermes_Gateway.cmd` runs `hermes gateway run` detached) — killing the gateway PIDs is enough; verify by PID creation-time being AFTER the config write (Win32_Process.CreationDate), not just PID existence. When the profile drives running cron/loop jobs (金策 30-min loop + scheduled nodes), state the trade-off: restart now (brief interruption, next cycle auto-recovers) vs. let the next natural restart pick it up. Never spawn/kill MT5 terminals during this — that's the IPC-crash class. **This host runs the single-gateway variant** (all locks same pid — see Live topology facts): there is no per-profile process to kill; state the same restart-now vs next-fire trade-off and hand the user the one-click bat for immediate cutover.

## Pitfalls
- **Programmatic splice must start the block on its own line**: when inserting provider blocks by text surgery (find the `\nfallback_providers:` anchor and insert before it), the block text must BEGIN with `\n` — otherwise its header glues onto the previous block's last line (`agnes-2.5-pro-beta: {}  agnes-pm-cn:`) and the whole config fails YAML parse with `expected <block end>, but found <scalar>` at the glued line. After ANY programmatic config edit, parse-verify: the hermes venv python HAS pyyaml (`E:/workbuddy/国外模型/hermes/installs/*/environments/*/venv/Scripts/python.exe -c "import yaml; yaml.safe_load(open(...))"` → gives line/column of the real error); the system pythons do not, and the hermes CLI reports a broken secondary profile with the misleading message 'could not parse plugin selection' when the actual root cause is a providers-section YAML syntax error.
- **YAML block misplacement by end-of-file append**: `providers:` and other sections in these configs are NOT at the file end — the file continues with `toolsets:`/`video_gen:`/`plugins:`. Appending a block to EOF lands it under the wrong top-level parent and is silently ignored by provider discovery. Insert inside the `providers:` section: locate the next top-level key line after the last existing provider block and insert before it. Verify by byte-offset comparison against the next top-level anchor.
- **No yaml module in SYSTEM python, but the hermes venv python HAS pyyaml**: verify every config.yaml edit with the venv interpreter (see pitfall above) instead of text-anchor checks; text anchors are only the fallback when even the venv is unavailable. Do not install packages mid-task just for verification.
- **Duplicate-slot noise**: if a prior session already added a `*_COM_NEW` slot + block, don't add a second parallel one — replace or reuse. "Keep the more complete side, delete the other" (user's standing dedupe rule).
- **Duplicate input/param-name collision (multi-round edits)**: when a second optimization round adds a same-named input/parameter already declared earlier, the compiler dies with error 125 (variable already defined) + error 282 (identifier already used) — check existing names BEFORE writing new declaration lines; remove the duplicate and re-add any removed one that later code still references.
- **Full-key literal in probe scripts**: placeholders like `sk-CJR...Bswp` produce false 401s that look like dead keys. Write the actual `.env` value into the probe script, mask only on display.
- **Idempotent fallback-appends**: when auto-wiring recovered keys back into `fallback_providers` (sentinel-style), the "already present" check must match the `- provider: <name>` ENTRY, not the section header — a header-only match makes every add a no-op and the wiring silently never happens.
- **Regex discipline in config surgery**: never place two inline global-flag groups (`(?m)…|(?m)…`) in one pattern — re raises 'global flags not at the start'; use one `(?m)` prefix over an alternation. Functions that rewrite a section return the new text only — don't unpack `t, flag = rewrite(t)` when it returns one value.
- **Two-pass allocation** (dedicated-key rounds): pass 1 keeps each seat's current `.env` value where it is in the available set (zero diff); pass 2 fills the rest from the available pool. Keeps the .env rewrite surface minimal and makes the round rollback-friendly.
