---
name: cn-client-pitch-deck
description: Use when making 李彦明 Chinese PPT pitch decks (客户汇报/产品介绍).
version: 1.0.0
author: Hermes
tags: [pptx, chinese, pitch-deck, client, cjk]
metadata:
  hermes:
    category: productivity
    related_skills: [powerpoint]
---

# Chinese Client-Facing Pitch Decks

Build a client-facing product/pitch deck for this user's AI-bot systems in Chinese: 16:9, dark + gold house palette, name-only attribution, plain-language lines, per-slide speaker notes, honest data framing. Deliverable goes to `E:\workbuddy\内容中心\交付\` (standing rule: all content lives under 内容中心).

## House spec (always on)

- **Name-only attribution**: presenter name (e.g. 李彦明) on cover, footer, closing slide. NO company / affiliation / org name anywhere in deck body or footer. If an architecture diagram has a top "user" node, label it `客户 / 决策者`, not the presenter's name.
- **Plain language (大白话)**: audience may not read code — pair every technical term or English abbreviation with a one-line plain wording. A jargon stack must land as a sentence a non-coder can follow.
  - **Touring / public-speaking standard raises this to removal, not pairing**: when the deck is for a live audience (全国巡回演讲, or any client-facing body the presenter will project), English filenames / module names / cron tokens / env-var names (e.g. `chief_pipeline.py`, `veto_log.json`, `meta_evolver`, `AGNES_KEY_*`, `daily_advisory.json`) must NOT appear in slide body — replace with a plain-language role/function label ("全链流水线", "留痕账本", "元进化引擎", "专属密钥（风控档）"). Keep the precise identifiers ONLY in the speaker notes, where the presenter reads them but the audience does not. The leak-scan token list therefore grows to include internal filenames/module names/env-var names for the BODY (the notes may keep them).
  - **The platform's own brand name and its CLI command syntax are a leak too, not just the project files**: a touring client deck that names the engine (e.g. "Hermes 界面", "hermes chat", "hermes doctor", "hermes profile create", the `curl ... | bash` install line) exposes the tech stack AND repels the audience — clients don't care what platform it runs on. For touring, scrub the platform brand name and every one of its command/flag/URL forms from the BODY and replace each with a plain Chinese role label (Hermes → "系统"; `hermes chat` → "后台对话"; `hermes doctor` → "系统体检"; `hermes profile create` → "后台一键新建一个 bot"; `hermes skin use` → "后台一键换外观"; `hermes config set` → "改配置走后台管理台"; install URL → "一条命令搞定"; `OAuth/token` → "身份验证"; `.env` → "密钥箱"; `config` → "设置"; `/model` → "换脑子"; `/reset` → "新开会话"; `TUI/CLI` → "终端/命令行"). The full mapping lives in `references/leak-token-list.md`. Same notes-vs-body rule: the real command names may stay in speaker notes, but the projected slide body must be jargon-free.
- **Speaker notes on every content slide**: written as the live talk track (sentences to say, not bullets). Tell the user to present in 演示者视图.
- **Honesty framing**: simulation / backtest / demo data carries a visible disclaimer (历史 ≠ 未来, 模拟 ≠ 实盘, 大动作先报后动).
- **Required arc**: 亮点 (one page each) → 与市面系统对比表 → 前沿科技对标 (backed by real evidence, not buzzwords) → 全行业扩展 (methodology + a per-industry blueprint table) → 数据 + 下一步建议 (3-option close: 打样 / 复制 / 陪跑).
- **Frontier slides need numbers**: named benchmark / paper / competition with dated, concrete results (e.g. a live-trading contest's win/loss figures). Do a web research pass before writing them; an unbacked claim is a weak slide.
- **Full-industry extension is a standing selling point**: the user repeatedly wants "能延伸到全行业" — always include a methodology page (copy the skeleton) AND a per-industry role-mapping table (who schedules / executes / vetoes / researches / which external event triggers a pullback).
- **Selling points first, how-tos last**: in a combined/merged deck, the client-attractive showcase (product/system: 痛点 → 亮点 → 市面对比 → 全领域市场 → 军团 → 蓝图 → 实证 → 价值主张) leads; operational how-to (interface/config/prompt/upgrade manuals) goes behind it. Exactly ONE closing slide for the whole deck — no mid-deck 谢谢聆听, no section boundaries that break the arc.
- **Make the narrative arc explicit so the audience isn't lost**: the user's standing complaint about a weak deck is "客户听了很混乱" (the confidence curve dips). Two concrete fixes: (a) add a near-front "why you'll stay / 信心爬升曲线" slide that draws the whole path as ascending rungs (each rung = a concept + "what the client will start to believe"), explicitly stating "先给信心（实打样品），后给工具（操作细节）"; (b) when the user asks to "把每个子 bot / 每个角色 全部细节深度解析", insert per-entity deep-dive pages into the FRONT showcase (right after the architecture/overview page), NOT into the back how-to section — confidence comes from the audience seeing the machine's innards (who's in it, what each does / does NOT do, its guardrails) up front. Use ONE reusable page template for all N entities so the series reads as a set, not scattered slides.

## User expectations for depth & iteration

The user repeatedly asks for "10+ 次优化升级" and expands scope mid-review (e.g. adding a new market/domain dimension). Plan for this:
- **Each named pass = one concrete, visible change** (a new slide, a new helper, a reworded block, a leak-scan result, a visual-QA confirmation). Don't bundle five changes under one pass name.
- **Structure for slot-in extension**: keep each section in its own build file (multi-part pattern in `references/cjk-python-pptx-toolkit.md`) so a new section = one import + one `build(d)` call + a renumber of the NOTES tail, not a full renumbering cascade.
- **The "全网顶级模板" bar** means every methodology claim ships with a copyable artifact — a 6-slot prompt, a step list, or a table the audience can lift off the slide and use today. A concept slide with no concrete artifact is a miss.

## Workflow (multi-pass, not one-shot)

The user expects repeated build → read-back → leak-scan → refine passes; a single delivery pass is a miss.

1. Gather source material (state cards, 分工 docs, READMEs) + do the frontier research before writing slides.
2. Author ONE build script (python-pptx; toolkit in `references/cjk-python-pptx-toolkit.md`) as the single source of truth — custom cards/geometry/tables beat the JSON-spec `pptx_create.py` script for CJK multi-card decks.
3. Build → `pptx_read.py OUT.pptx --outline > outline.json` → verify slide count, texts, tables, notes.
4. **Leak scan** (both families — project internals AND the platform's own brand/CLI syntax; token list + plain-label replacements in `references/leak-token-list.md`; match credentials on word boundaries, not substring): join every text + table cell into one string; search for forbidden tokens (org names, credentials, internal absolute paths, platform brand + command forms) and confirm required ones (presenter name appears only as name, disclaimer present, user node labeled 客户/决策者).
5. Refine in the build script, rebuild. Never hand-edit the .pptx.
5a. **A content fix is not done until the SHIPPED .pptx is re-scanned and clean.** After any wording/sanitization pass, the build script is only the source of truth — the .pptx the user will hand to a client still holds the OLD text until you re-run the build and overwrite the file. Sequence: edit source → rebuild → grep the SOURCE files for the removed token (confirm zero) → re-run the leak-scan on the SHIPPED .pptx for the same token → render + vision QA → only then call it done and report. 'I removed it from the source' is a false claim while the pptx still contains it; an un-rebuilt deliverable is a live leak on stage. If the build script was already run and the source now shows zero but the pptx scan still hits, the rebuild step was the one that didn't happen.
6. Deliver to 内容中心/交付 with a short report: what changed, what's verified, slide count + arc, plus the presenter-view tip.
7. **Combined deliverable** (user asks 合成一份交付 / 把 X 放到最前面): merge the built decks at the OOXML/zip level and reorder by rebuilding `<p:sldIdLst>` only; then renumber the footer textboxes to the new order and re-run leak-scan + render QA on the merged file. Procedure and the duplicate-part trap live in `references/cjk-python-pptx-toolkit.md` (merge section).

## Pitfalls

- **East-Asian font fallback**: `run.font.name` sets only the Latin typeface; Chinese renders via the East-Asian (`a:ea`) typeface and silently falls back to a default CJK font — the usual cause of a deck that "looks cheap" on the client's screen. Set `a:ea` on every run (helper in the toolkit).
- **Read-back table shape**: in `pptx_read.py --outline` JSON, `tables` are nested `[[cell,...],...]` lists, not `{rows: ...}` objects. Iterate `for row in tb:` — `tb["rows"]` raises `TypeError`.
- **Windows/MSYS text capture**: the outline CLI prints non-ASCII JSON; redirect to a file and `open(path, encoding="utf-8")`. Piping through `head` or a `subprocess` harness mangles/truncates it; loading the skill script via `exec_module` is fragile. Run the CLI directly in the terminal.
- **Frontier claims without numbers**: a cutting-edge slide that names a trend with no dated benchmark / result is a buzzword slide. Back it.
- **A 'clean' source grep proves nothing about the shipped file**: scanning the build scripts for a forbidden token and getting zero hits does NOT mean the .pptx is clean — the token is baked into the pptx at build time and only disappears on the next rebuild. The leak-scan must be re-run against the .pptx (python-pptx text + table iteration) after every build, and the pass/fail gate is that re-scan, not the source grep. Two separate artifacts, two separate checks.
- **Match secret/leak tokens on word boundaries, not substring, or the scan is false-positive noise**: a naive `'sk-' in text` flags the plain word "risk-sop" inside `golden-strategy-risk-sop` and burns a QA cycle on nothing. Match credential-style prefixes with a boundary (`re.search(r'sk-[A-Za-z0-9]{6,}', text)` = a real key; bare `sk-` = likely a fragment of an English word), and verify any hit before patching. The same applies to short tokens like `cli`, `os`, `key` that appear inside ordinary English — anchor them to command/flag usage, not to raw substring.

## Verification

1. Slide count matches the arc; every content slide has a note.
2. Leak scan clean: zero org / credential / internal-path tokens; presenter name only as name; disclaimer present.
3. **Render PNGs on this Windows box WITHOUT LibreOffice**: PowerPoint COM via comtypes (the project venv has it; execute_code's sandbox python does NOT). Run via `terminal`:
   ```python
   import comtypes.client as cc
   ppt = cc.CreateObject("PowerPoint.Application"); ppt.Visible = 1
   ppg = ppt.Presentations.Open(r"E:\...\deck.pptx", WithWindow=0)
   ppg.SaveAs(r"E:\...\render_dir", 18)   # 18 = ppSaveAsPNG -> one PNG per slide
   ppg.Close(); ppt.Quit()
   ```
   PowerPoint names the PNGs `幻灯片N.PNG` (non-ASCII, e.g. 幻灯片1.PNG) — sort by the integer in the filename via regex, not raw name. Then `PIL.Image` (the project venv has it) to tile N slides into one contact sheet, and `vision_analyze` the sheet.
   **Treat vision flags as hypotheses, not facts — verify before patching.** At thumbnail scale the vision model not only misreads page numbers but can *invent* text that does not exist (it has reported residual code/filenames the source never contained). Before acting on ANY content-level flag (residual leak, overflow, truncation, "still has English jargon"): (1) `grep` the build scripts for the exact claimed token, and (2) extract the real text from the .pptx (`pptx_read.py --outline` or python-pptx shape iteration) and search that. Only patch text you can actually find. Never chase a vision hallucination by "fixing" copy you cannot locate in the source.
4. If neither PowerPoint nor LibreOffice is available, fall back to the JSON outline from `pptx_read.py`.
