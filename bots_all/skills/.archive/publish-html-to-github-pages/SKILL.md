---
name: publish-html-to-github-pages
description: Use when 把本地 HTML 文件发布成可分享的 GitHub Pages 公网链接。
---

# 发布本地单文件 HTML 到 GitHub Pages(可分享链接)

Class of task: turn a local self-contained HTML artifact (dashboard, report, single-file teaching page) into a public URL the user can forward to anyone, and keep it live by auto-syncing the source into a public repo. On this host the user is on Windows/MSYS (git-bash), and the target audience opens the link in a browser with no login.

## User preferences (李彦明, standing)
- **Self-contained single file is the deliverable** — the artifact must work from `file://` and have **no CDN externals** (offline-capable is the norm here). A GitHub Pages host serves it fine as-is.
- **Never publish more than the one artifact.** The public repo gets ONLY the shareable HTML (as `index.html`). Anything that could carry live data, strategy logic, P&L, MT5 passwords, or API keys stays out of the public repo — even when the source and the sensitive material sit in the same directory tree. Build the publish repo from a **separate scratch dir**, not by git-init'ing the source directory.
- **The link stays current, not a frozen snapshot.** A Pages URL only updates when you push. If the source is regenerated on a schedule, wire a sync step into that schedule so the shared link tracks the latest content; report that the link is "real-time (up to one refresh cycle stale)" not "a fixed snapshot."
- **Report the shareable URL plainly** — one screen: the URL, that it needs no login, what it shows, and how to take it down later (make repo private / delete Pages). 大白话, not a process replay.

## Procedure
1. **Security pre-check on the artifact BEFORE publishing.** Grep the file for secrets/identifiers that must not hit a public URL: CDN/external `src=`/`href=`, `sk-`/`Bearer`/`api_key`/`password=` strings, and account IDs. If clean (no externals, no secrets, no account IDs), proceed. If a secret is embedded, fix the source to strip it — do NOT scrub-and-publish (the source still has it and the next sync re-leaks it).
2. **Build an isolated public repo** in a scratch dir (`mkdir + git init`), copy ONLY the artifact in as `index.html`, commit. Do not `git init` the source tree.
3. **Create the public repo + push + enable Pages** (commands below). Expect the github.com network to flake on this host — wrap the push in a retry loop and verify the remote actually has the commit (see gotcha #4).
4. **Verify the public URL live** with a real HTTP fetch: expect `200` + a body byte-count matching the source + the expected `<title>`. A 200 with an empty/short body = network flake, retry; don't declare success on the Pages `status: built` alone.
5. **Wire auto-sync** (only if the source is regenerated on a schedule): hook a small idempotent sync step into that schedule. Use `templates/sync_pages.py` as the starter — it is failure-safe (records the last-SUCCESS mtime; only re-pushes when the source is newer; re-pushes on network failure instead of swallowing the pending update). For a schedule that is itself a Python pipeline, add a `subprocess.run([sys.executable, SYNC, "--quiet"], timeout=240)` step at the END that is **best-effort** (try/except, never affects the pipeline's return code) — the trading/main chain must keep running even if a push flakes.
6. **Report** the URL + "no login, shows X, takes up to one refresh cycle to update, to remove: <one command>".

## Commands (gh first; this host has `gh` authenticated as `dapengzhanchi141345`)
```bash
# 1) scratch repo with only the artifact
cd /c/Users/ASUS && rm -rf <name> && mkdir <name> && cd <name>
cp "E:/path/to/artifact.html" index.html
git init -q && git add index.html && git commit -m "publish"
git branch -M main          # git init here defaults to master; Pages+push expect main

# 2) create public repo + push (retry: github.com flakes on this host)
gh repo create <owner>/<name> --public --source . --remote origin --push
for i in 1 2 3 4 5; do
  git push -u origin main >/dev/null 2>&1
  git ls-remote origin main >/dev/null 2>&1 && break; sleep 8
done

# 3) enable Pages (source must be an OBJECT, not a string, or 422)
PAYLOAD="$LOCALAPPDATA/Temp/pages_payload.json"
printf '%s' '{"build_type":"legacy","source":{"branch":"main","path":"/"}}' > "$PAYLOAD"
gh api -X POST repos/<owner>/<name>/pages --input "$PAYLOAD"
# 4) poll until built (takes ~1-2 min)
for i in 1 2 3 4; do sleep 30
grep -aoE '"status":"[^"]*"' <(gh api repos/<owner>/<name>/pages) | tail -1
done

# 5) verify live (a real browser-like fetch, not just the Pages status)
python -c "import urllib.request as u; r=u.urlopen('https://<owner>.github.io/<name>/', timeout=40); b=r.read(); print(r.status, len(b))"
# share link: https://<owner>.github.io/<name>/
```

## Windows / MSYS gotchas (this host — these are NOT in the bundled github skills)
1. **Native `gh`/`git` cannot read `/tmp`** — MSYS's `/tmp` is a virtual path; write `gh api --input` payload files to `$LOCALAPPDATA/Temp/...` (a real `C:\Users\<user>\AppData\Local\Temp\...`) instead, or gh fails with `The system cannot find the file specified.`
2. **`git init` defaults the branch to `master`**, so `git push origin main` / Pages `branch:main` fail with `src refspec main does not match any`. Always `git branch -M main` first.
3. **A green-looking "push succeeded" echo is not proof.** This host flaps github.com (DNS via aliyun DoH, occasional 443 reset). A loop that echoes success on `git push` exit can lie. Authoritative check = `git ls-remote origin main` returns a commit hash.
4. **Pages `source` is a JSON object.** Passing the source as a quoted string (`-f source='{...}'`) → `422 Invalid property /source ... is not of type object`. Use `--input file.json` (see step 3).
5. **Network flake = retry with backoff, not a new failure.** Re-run the push/poll a few times with sleeps; a 200/`built` on a later attempt is the expected pattern. Don't write down "github is broken here" — the retry clears it.

## When git-push is 443-walled: gh-api fallback route
When the host's git/https lane to github.com flaps (443 resets, DNS via DoH) so the standard push loop never lands, fall back to pushing a file **through `gh api` to api.github.com directly** (a different host, often reachable when github.com isn't). Content-addressed rebuild, no local clone needed:
```bash
BLOB=$(gh api -X POST repos/OWNER/REPO/contents/$FILE --input payload.json | jq .content.sha)
gh api -X PUT repos/OWNER/REPO/git/trees/$TREE -f sha=$TREE -f "tree[]=$FILE:$BLOB" # or add one entry to the existing tree
gh api -X POST repos/OWNER/REPO/git/commits -f message=sync -f tree=$TREE -f parents[]=$HEAD
gh api -X POST repos/OWNER/REPO/git/refs -f ref=refs/heads/main -f sha=$NEWCOMMIT
```
Rules:
- **Verify reachability first** — probe `gh api repos/OWNER/REPO` once; if api.github.com is also walled, fail-open: keep the pending update, retry on the next scheduled tick, never strand it (same "stamp success only on verified push" rule as the sync template).
- Strip any `.git` suffix from a `OWNER/REPO` variable before building gh-api paths — the literal `repo.git` in the path 404s on the REST API even though git-push would accept it.
- Keep the normal git-push route as primary; the gh-api lane is the fallback, not a replacement. It must be wired into the existing sync guard as one more path among its retry set, not a parallel dashboard chain.

## Two-time-constancy for live dashboards (prices must look alive, not frozen)
When a dashboard is regenerated by a slow scheduled chain (e.g. 30min full recompute) but the user reads it as a live board, the static snapshot will look frozen between cycles and gets reported as "not updating". Fix: **decouple a fast data feed from the slow chain**:
- A short-cycle deterministic job (5–10min, 0 LLM) live-reads the data (e.g. broker ticks) → writes one small JSON (`tick_live.json`) → pushes it through the same sync lane.
- Inject **once into the GENERATOR** (the script that writes the HTML) a self-contained polling script that fetches that JSON every ~60s and renders it in a floating live bar with a "N s ago" timestamp; on fetch failure degrade to "showing snapshot prices", never blank, never crash the page.
- The slow full chain keeps doing its job (analysis/k-lines/trading) untouched — the fast feed is display-only and must never gate or touch the trading chain.
- Because the HTML is regenerated by the slow chain, the polling script lives in the generator output; a one-off edit of the published HTML gets clobbered on the next cycle (existing pitfall, it applies again here).

## Pitfalls
- Publishing the source directory (or a repo that also holds engine/data/credentials) instead of an isolated single-file repo = leaking live data to a public URL. The isolation in step 2 is the safeguard; re-check `git status` shows only `index.html` before the first push.
- Forgetting auto-sync → the shared link silently freezes at the publish-time snapshot while the source keeps regenerating. Hook the sync into the SAME schedule that regenerates the source.
- A sync step that records "synced" on FAILURE: if you stamp success before the push actually lands, the next run sees no mtime change and skips forever, so a flaky-push window permanently strands the update. Only stamp on a verified successful push; on failure keep the old stamp so the next run re-pushes.
- **Assuming the 30-min (or whatever) regeneration keeps the page "live" for a price board.** A static file only refreshes on push; a human reads it as frozen in between. If the board shows prices, wire the two-time-constancy fast feed + in-page polling above; verify by fetching the pushed live-JSON from the public repo, not just scheduling the job.
- **Static footer / injected marker gets clobbered by the regenerator.** If the artifact is regenerated on a schedule, a footer/signature you add by editing the output `.html` directly disappears on the next cycle. Inject the marker into the GENERATOR (the script that writes the HTML), then re-run the generator and push manually once — never rely on a one-off edit to the output file.

## PPT deck → online slideshow (user asks to "deploy to a URL I can open")
When the deliverable is a .pptx the user wants viewable in a browser, publish a single-file slideshow, not the pptx itself:
1. Render the pptx to PNGs with PowerPoint COM (not LibreOffice — `soffice` is NOT on this host's PATH and a global `find` for it hangs): `ppt=cc.CreateObject("PowerPoint.Application"); pp=ppt.Presentations.Open(pptx,1); pp.SaveAs(render_dir,18); pp.Close()` then `taskkill //F //IM POWERPNT.EXE`.
2. Build a self-contained slideshow `index.html`: JPEG-compress each page (~width 1600, q85 → ~90-110KB/page; a 79-page deck ≈ 10MB, under GitHub's 50MB per-file limit), inline every image as base64 (NO CDN — user rule), add keyboard (←/→/space/f/Home/End) + swipe + a thumbnail index grid + hash deep-link (`#42` jumps to page 42). Pull each page's nav title from the PPT's first run with `font.size>=28pt`.
3. Deploy with the standard procedure below (isolated scratch repo, only `index.html`). The pre-publish grep check still applies — a base64-inlined deck is still one artifact.

## References
- `references/deck-slideshow-deploy.md` — PPT→PNG→base64-slideshow pipeline for the "deploy deck to a URL" class
- `templates/sync_pages.py` — known-good idempotent + failure-safe source→Pages sync step; copy, edit SRC/REPO paths, drop into the source's regeneration schedule.
