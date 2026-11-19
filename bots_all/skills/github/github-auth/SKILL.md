---
name: github-auth
description: "GitHub auth setup: HTTPS tokens, SSH keys, gh CLI login."
version: 1.1.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [GitHub, Authentication, Git, gh-cli, SSH, Setup]
    related_skills: [github-pr-workflow, github-code-review, github-issues, github-repo-management]
---

# GitHub Authentication Setup

This skill sets up authentication so the agent can work with GitHub repositories, PRs, issues, and CI. It covers two paths:

- **`git` (always available)** — uses HTTPS personal access tokens or SSH keys
- **`gh` CLI (if installed)** — richer GitHub API access with a simpler auth flow

## Detection Flow

When a user asks you to work with GitHub, run this check first:

```bash
# Check what's available
git --version
gh --version 2>/dev/null || echo "gh not installed"

# Check if already authenticated
gh auth status 2>/dev/null || echo "gh not authenticated"
git config --global credential.helper 2>/dev/null || echo "no git credential helper"
```

**Decision tree:**
1. If `gh auth status` shows authenticated → you're good, use `gh` for everything
2. If `gh` is installed but not authenticated → use "gh auth" method below
3. If `gh` is not installed → use "git-only" method below (no sudo needed)

---

## Method 1: Git-Only Authentication (No gh, No sudo)

This works on any machine with `git` installed. No root access needed.

### Option A: HTTPS with Personal Access Token (Recommended)

This is the most portable method — works everywhere, no SSH config needed.

**Step 1: Create a personal access token**

Tell the user to go to: **https://github.com/settings/tokens**

- Click "Generate new token (classic)"
- Give it a name like "hermes-agent"
- Select scopes:
  - `repo` (full repository access — read, write, push, PRs)
  - `workflow` (trigger and manage GitHub Actions)
  - `read:org` (if working with organization repos)
- Set expiration (90 days is a good default)
- Copy the token — it won't be shown again

**Step 2: Configure git to store the token**

```bash
# Set up the credential helper to cache credentials
# "store" saves to ~/.git-credentials in plaintext (simple, persistent)
git config --global credential.helper store

# Now do a test operation that triggers auth — git will prompt for credentials
# Username: <their-github-username>
# Password: <paste the personal access token, NOT their GitHub password>
git ls-remote https://github.com/<their-username>/<any-repo>.git
```

After entering credentials once, they're saved and reused for all future operations.

**Alternative: cache helper (credentials expire from memory)**

```bash
# Cache in memory for 8 hours (28800 seconds) instead of saving to disk
git config --global credential.helper 'cache --timeout=28800'
```

**Alternative: set the token directly in the remote URL (per-repo)**

```bash
# Embed token in the remote URL (avoids credential prompts entirely)
git remote set-url origin https://<username>:<token>@github.com/<owner>/<repo>.git
```

**Step 3: Configure git identity**

```bash
# Required for commits — set name and email
git config --global user.name "Their Name"
git config --global user.email "their-email@example.com"
```

**Step 4: Verify**

```bash
# Test push access (this should work without any prompts now)
git ls-remote https://github.com/<their-username>/<any-repo>.git

# Verify identity
git config --global user.name
git config --global user.email
```

### Option B: SSH Key Authentication

Good for users who prefer SSH or already have keys set up.

**Step 1: Check for existing SSH keys**

```bash
ls -la ~/.ssh/id_*.pub 2>/dev/null || echo "No SSH keys found"
```

**Step 2: Generate a key if needed**

```bash
# Generate an ed25519 key (modern, secure, fast)
ssh-keygen -t ed25519 -C "their-email@example.com" -f ~/.ssh/id_ed25519 -N ""

# Display the public key for them to add to GitHub
cat ~/.ssh/id_ed25519.pub
```

Tell the user to add the public key at: **https://github.com/settings/keys**
- Click "New SSH key"
- Paste the public key content
- Give it a title like "hermes-agent-<machine-name>"

**Step 3: Test the connection**

```bash
ssh -T git@github.com
# Expected: "Hi <username>! You've successfully authenticated..."
```

**Step 4: Configure git to use SSH for GitHub**

```bash
# Rewrite HTTPS GitHub URLs to SSH automatically
git config --global url."git@github.com:".insteadOf "https://github.com/"
```

**Step 5: Configure git identity**

```bash
git config --global user.name "Their Name"
git config --global user.email "their-email@example.com"
```

---

## This Windows box: `gh` is not on the default PATH
On this host `gh` was installed by hand to `C:\Users\Administrator\ghbin\bin\gh.exe` (winget install hung, so a manual binary download to `ghbin`). It is NOT on the cron/scheduled-job session's default PATH, so a bare `gh` call from a scheduled job dies with `WinError 2 系统找不到指定的文件`. The 金策 GitHub scripts (`jince_tick_push.py`, `jince_dashboard_sync_guard.py`, `jince_github_sync.py`, `sites_deploy_12indep.py`, `skills_github_sync.py`) all invoke `gh` via that absolute path (with a bare-`gh` fallback). To unblock the 5 金策 GitHub push jobs, the user supplies a PAT for `dapengzhanchi141345` and the agent runs `echo <token> | & 'C:\Users\Administrator\ghbin\bin\gh.exe' auth login --with-token` then `gh auth setup-git`. Until that token arrives the jobs fail at the `gh api` auth step while local writes still succeed.

**Token-death recovery loop (sentinels retrying `gh auth login` every 10 min):** when dashboards/tick-push sentinels start failing with "gh auth login / GH_TOKEN" while local writes succeed, the PAT is dead. Do NOT keep re-running the failing cron — ask the user once for a fresh classic token (github.com/settings/tokens/new, `repo` scope, name `jince-gh-sync`, paste the `ghp_…` into chat), then: `echo "<token>" | & '<ghbin>\gh.exe' auth login --with-token` (lands in the Windows keyring, survives reboots) → `gh api user` (expect the login name, e.g. `dapengzhanchi141345`) → re-run each sync script ONCE → verify the remote (recursive blob count / `pushed_at` / latest commit message). Sentinels clear themselves after that; a keyring login survives reboots so the cycle repeats only when the PAT expires. **The 11-05 recovery succeeded end-to-end** (token in keyring, jince-work-ledger 61-file push incl. skills/, tick_push + dashboard guard back to exit 0): treat "sentinels failing on gh auth" as the token's expiry alarm, not a network/443 verdict — `gh auth status` (expect "not logged in") distinguishes it from a wall in one command.
**Portability pitfall (11-05): hardcoded username-home paths kill scripts cross-host.** `jince_github_sync.py` wrote its log to a hardcoded `C:\Users\ASUS\AppData\Local\Temp` path — on any host where that user dir does not exist the script pushed successfully and then crashed in the final `open(LOG, "a")` (WinError 267 family), making a good run look failed. It is patched to `os.path.join(tempfile.gettempdir(), …)`. The same family hit `jince_tick_push.py` + `jince_dashboard_sync_guard.py` (`REPO = C:\Users\ASUS\jince-dashboard` — used for local stamp files; Errno 2 on every run on this host): patched to `os.environ.get("JINCE_DASH_REPO", r"E:\workbuddy\金策宗师团\_github_mirror\jince-dashboard")` + `os.makedirs(REPO, exist_ok=True)`. Rule for any new 金策 GitHub script: build log/cache/stamp/repo-local paths from env override or `tempfile.gettempdir()`, never from a remembered username home.

## Method 2: gh CLI Authentication

If `gh` is installed, it handles both API access and git credentials in one step.

### Interactive Browser Login (Desktop)

```bash
gh auth login
# Select: GitHub.com
# Select: HTTPS
# Authenticate via browser
```

### Token-Based Login (Headless / SSH Servers)

```bash
echo "<THEIR_TOKEN>" | gh auth login --with-token

# Set up git credentials through gh
gh auth setup-git
```

### Verify

```bash
gh auth status
```

---

## Using the GitHub API Without gh

When `gh` is not available, you can still access the full GitHub API using `curl` with a personal access token. This is how the other GitHub skills implement their fallbacks.

### Setting the Token for API Calls

```bash
# Option 1: Export as env var (preferred — keeps it out of commands)
export GITHUB_TOKEN="<token>"

# Then use in curl calls:
curl -s -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/user
```

### Extracting the Token from Git Credentials

If git credentials are already configured (via credential.helper store), the token can be extracted:

```bash
# Read from git credential store
grep "github.com" ~/.git-credentials 2>/dev/null | head -1 | sed 's|https://[^:]*:\([^@]*\)@.*|\1|'
```

### Helper: Detect Auth Method

Use this pattern at the start of any GitHub workflow:

```bash
# Try gh first, fall back to git + curl
if command -v gh &>/dev/null && gh auth status &>/dev/null; then
  echo "AUTH_METHOD=gh"
elif [ -n "$GITHUB_TOKEN" ]; then
  echo "AUTH_METHOD=curl"
elif _hermes_env="${HERMES_HOME:-$HOME/.hermes}/.env"; [ -f "$_hermes_env" ] && grep -q "^GITHUB_TOKEN=" "$_hermes_env"; then
  export GITHUB_TOKEN=$(grep "^GITHUB_TOKEN=" "$_hermes_env" | head -1 | cut -d= -f2 | tr -d '\n\r')
  echo "AUTH_METHOD=curl"
elif grep -q "github.com" ~/.git-credentials 2>/dev/null; then
  export GITHUB_TOKEN=$(grep "github.com" ~/.git-credentials | head -1 | sed 's|https://[^:]*:\([^@]*\)@.*|\1|')
  echo "AUTH_METHOD=curl"
else
  echo "AUTH_METHOD=none"
  echo "Need to set up authentication first"
fi
```

---

### Restricted networks (GitHub blocked at DNS/TCP, but api.github.com or DoH works)
When `nslookup github.com` times out / `curl github.com` fails but `api.github.com` works (typical GFW-style interference):

1. `gh auth login --web` / device-code will fail — they hit `github.com/login/*`. Use **PAT instead**: user generates a classic token on any reachable device, then `echo "<token>" | gh auth login --with-token && gh auth setup-git`.
2. git's network stack still can't resolve `github.com`. Fix with git 2.54+ external DNS:
   - `git config --global nameResolution.provider 'C:/path/resolve-dns.bat'` — the provider is executed VERBATIM (no shell parsing), so on Windows wrap in a `.bat`/`.exe`; `"python script.py"` in one quoted string fails.
   - Script: query `https://223.5.5.5/resolve?name=<host>&type=A` (aliyun DoH JSON), print A-records, exit 1 on empty.
   - The DoH IPs may themselves be TCP-blocked — probe candidate IPs with `curl --resolve host:443:IP` first; if the canonical IP range fails but others work, hardcode a per-host override table inside the script.
   - Verify: `GIT_CURL_VERBOSE=1 git ls-remote <repo>` should show `Host was resolved` → `IPv4: <ip>` → `HTTP/1.1 200` on `info/refs`.
3. Interference is often intermittent: a failing `ls-remote` may pass 3 attempts later. Treat one failure as 'retry', not 'broken'.

Note: `git config --get-regexp '^credential\.'` reveals `gh auth setup-git` writes `credential.https://github.com.helper '!gh auth git-credential'` — git then authenticates via gh's token store, no separate git credentials needed.

## Pushing via `gh api` when `git push` is 443-walled (Windows GFW + DoH)

When `git push` to `github.com:443` times out but `api.github.com` is reachable (DoH resolves it), push over the REST **git data API** instead of git — no clone, no network stack fix needed. The 金策 nightly sync does exactly this: `E:\workbuddy\国外模型\hermes\scripts\jince_github_sync.py` (run `all|jince-sass|jince-ledger`), 03:00 cron, content-hash cache so only changed files re-upload, fails loud. Reuse it; don't re-derive.

**Recipe (one repo):**
0. Create the repo first if it does not exist: `POST user/repos` with `{"name":..., "private":true}`. Do NOT post to `repos/O/R` with a body — that is the UPDATE endpoint and returns 404 when the repo does not exist, which is indistinguishable from the provisioning 404s of Pitfall 2 and wastes a debug cycle.
1. Upload blobs: `POST repos/O/R/git/blobs` with `{"content": <base64>, "encoding":"base64"}` → returns blob `sha`. Cache `{sha256(file): blob_sha}` so nightly runs skip unchanged files (the 2000+ file case only pays for diffs).
2. Build the tree: `POST repos/O/R/git/trees` with `{"tree":[{path,mode:"100644",type:"blob",sha}]}`.
3. Commit: `POST repos/O/R/git/commits` with `{"message","tree":<tree_sha>,"parents":[<current HEAD sha>]}` (read HEAD from `GET .../git/ref/heads/main` first; `parents=[]` only on the very first commit).
4. Update ref: `POST repos/O/R/git/refs/heads/main` with `{"sha":<commit_sha>}`. **Do NOT use `"force":true` on the sync path** — a non-force update fast-forwards and a real divergence surfaces as an error you must see. (A one-shot full-rebuild script may force; the recurring sync must not.)
5. Verify by `GET .../git/trees/main?recursive=1` and count `type=="blob"` entries — must equal your local `git ls-files` count (minus exclusions). Don't trust the script's "success" alone.

**Pitfall 1 — empty-repo deadlock (409 on ALL git data endpoints).** A repo with ZERO commits returns `409 "Git Repository is empty"` on `git/blobs`, `git/trees`, `git/commits`, and `git/refs`. You **cannot** seed the first commit through the git data API. The only unlock is the **Contents API**: `POST repos/O/R/contents/README.md` with `{"message","content":<base64>}` — it works on a truly empty repo and creates the first commit + default branch; after that the git data API comes alive.

**Pitfall 2 — Contents API 404 after `POST user/repos`: git-backend provisioning is slow and unpredictable.** GitHub provisions the git backend asynchronously: for a while after repo creation, Contents POST returns `404` even though `GET repos/O/R` (metadata) already says the repo exists with `size:0` and `default_branch` set. Observed provisioning spans run from under a minute to 60+ minutes (a brand-new repo name was still not landed an hour after creation) — do not assume a fixed upper bound, and never delete+recreate hoping it lands faster. **Diagnose by endpoint behavior:** `git/*` endpoints returning `409 "Git Repository is empty"` = backend exists but has zero commits, and the Contents seed is the only unlock; Contents returning `404` = backend not provisioned yet, so wait. **Isolate the suspect before concluding a repo is stuck:** run the same `git/blobs` POST against a known-good repo (one that already has commits, e.g. the sync target sibling) — success proves the token + api.github.com path are healthy and the problem is that one repo's provisioning, not your credentials; a failure there redirects the diagnosis to auth/network. **Never spawn a second throwaway "probe" repo to test provisioning** — it creates a duplicate mirror target that the sync script would have to be re-pointed at, and it costs its own delete+cooldown; re-probe the same repo on later cron boundaries instead. **Durable handoff pattern:** run a bounded watchdog loop (e.g. 20 × 5 min) that retries the Contents seed and pushes the full payload automatically the moment it lands, with the recurring cron job as final backstop; keep the payload mirrored locally first so nothing is lost while waiting. A one-shot interactive session must not block on the wait — report the handoff state and move on.

**Pitfall 3 — nested trees must be built bottom-up; root depth = -1.** `git/trees` only accepts the *direct* children of one tree — you cannot post a path like `"a/b/c"` in a single call. For N files spread over a dir hierarchy: post each leaf directory's tree first, keep its returned sha, reference it in the parent as `{path:<dirname>, mode:"040000", type:"tree", sha:<sub_sha>}`, then post the root last. A real bug that cost a session: computing directory depth as `depth = d.count("/") if d else 0` makes the root **and** level-1 dirs both 0, so a `reverse=True` sort does not guarantee the root is built last — the root tree silently drops all its subdirectories and you end up with only the top-level files (e.g. 13 blobs instead of 2220). Fix: `depth = (d.count("/") if d else -1)` so the root is always last. The same silent-drop failure also shows up as an off-by-one in *which* dirs you register: for a path `a/b/c.py`, every intermediate level must be registered at its own level (`a` as a child of the root, `a/b` as a child of `a`) — a loop that registers only the immediate parent of each file drops entire sub-branches while every tree POST still returns 201 and no error is raised; only the recursive blob count against the local file count reveals the loss, and a mismatch points at missing parent→child dir references, not at re-uploading blobs. After any tree change, re-verify with `recursive=1` blob count before calling it done.

**Pitfall 4 — exclude git submodules / upstream vendor dirs.** `git ls-files` lists a submodule path as a single entry; the file API can't fetch its contents (you'll get `Permission denied` opening a gitlink, or a 409). If the working copy has `vendor/` (or similar) that is upstream code, not yours, exclude it by path prefix before uploading.

**Pitfall 5 — a diverged local clone makes `git push` always reject, and a sentinel misreports it as a "443 wall".** If a *separate* process (e.g. a 5-min tick-live pusher) writes to the same repo while a local `git` clone never pulls, the clone drifts thousands of commits behind; `git push` then returns `rejected (fetch first)` every time — not a network failure. A push-sentinel that only probes `git push` + DoH IPs will conclude "all paths dead / 443 wall" when the real cause is divergence. Diagnose before accepting the wall verdict: `gh api repos/O/R/rate_limit` (healthy core余量 = the api.github.com path is alive) and `gh api repos/O/R/commits/main` (does the remote already have newer content? if so, your "pending" push is stale). **Fix for a single HTML dashboard: skip the local clone entirely and PUT the file via the Contents API** — `GET repos/O/R/contents/index.html` for its current `sha`, then `PUT repos/O/R/contents/index.html` with `{"sha":<current>, "content":<base64>, "message":...}` (one call, no clone, no wall). Update the local `.last_synced` stamp after so the sentinel stops re-alarming. Longer-term, point the sentinel at a Contents-API PUT, not `git push`, when the repo is shared with a writer.

**Pitfall 6 — 金策 sync scripts: run under python 3.11, not the default 3.14 — EXCEPT a jince-ledger manual push verified fine under 3.14.** `jince_github_sync.py` (and siblings) import `zoneinfo.ZoneInfo("Asia/Shanghai")`; the default `python` (3.14) here lacks the `tzdata` package and throws `ZoneInfoNotFoundError: No time zone found with key Asia/Shanghai` — a crash that looks like the script is broken but is just the wrong interpreter. Invoke explicitly with the 3.11 interpreter, or `pip install tzdata`. Re-running a 金策 GitHub-sync script under bare `python` and seeing a tz error is the wrong-interpreter signal, not a script failure. Observed exception: a `jince-ledger` push (61 files incl. skills/ + 引擎决策 jsons) ran clean under bare `python` (3.14) on this host — tzdata clearly present enough for that code path; the 3.11 iron rule still governs the scheduled 03:00 cron.

## Pushing an arbitrary local tree that is not a 金策 repo (mirror pattern)

`push_via_api(dirpath, repo, branch, tag, excludes)` in `jince_github_sync.py` is a generic "ship this local git working copy to a GitHub repo over the git-data API" engine, not 金策-specific — reuse it to upload *any* directory (e.g. the whole Hermes skills tree) to a repo under a 443 wall:

1. The source tree is usually **not** a git repo. Build a throwaway mirror: `git init -b main`, copy the target files into it (filter junk: `.curator_backups/`, `__pycache__/`, `.venv/`, `*.pyc`), then `git add -A && git commit`.
2. `import sys; sys.path.insert(0, r"E:\workbuddy\国外模型\hermes\scripts"); from jince_github_sync import push_via_api` and call `push_via_api(mirror, "repo-name", "main", "tag", excludes=(...))`.
3. It is **idempotent + resume-safe**: blobs are cached by content sha256, so a run that dies mid-stream resumes where it left off on re-run (only the diff uploads). Confirm completion by the remote ref sha / `pushed_at`, not the script's exit alone.

**Pitfall 7 — a full-tree POST prunes any remote path missing from the mirror.** `push_via_api` builds the commit from your *entire local tree*; applied on top of the parent commit, every path absent from that new tree is **deleted**. A sync that mirrors only part of the repo (or rebuilds from a filtered copy) silently nukes root-level files you didn't copy — `.gitignore`, a ledger, a seed. Before pushing, re-fetch any root-level infra you must keep into the mirror (`gh api repos/O/R/contents/<file>` → base64-decode → write), so it is present in the tree and survives the POST.

**Pitfall 8 — a few-thousand-blob payload must run in the background, not foreground.** A gh-api blob upload of a large tree easily exceeds the 600s foreground `terminal` cap and gets cut off mid-stream with nothing pushed yet (remote ref still old, no new commit). Because the content-hash cache makes re-runs resume cleanly, start the push with `background=True` (or a cron) and poll remote `pushed_at` + the on-disk blob-cache file's key count to confirm completion.

**Interpreter:** importing `jince_github_sync` executes its module-level imports; run the importing script under the **same interpreter the 金策 scripts use** (Pitfall 6), not the default one that lacks `tzdata`.

**Pitfall 9 — GitHub commit timestamps are UTC; "did it push this morning?" must convert to local before judging.** `gh api repos/O/R/commits/heads/main --jq .commit.committer.date` returns an ISO timestamp suffixed `Z` (= UTC). Comparing it against a *local* date without converting is off by the UTC offset (UTC+8 = −8h): a push at local 02:00 reads as `…T18:00Z` on the *previous* UTC day, so a freshness check that tests `startswith(today_local_date)` falsely reports STALE / "not pushed" even though every repo just landed. Convert first (`datetime.fromisoformat(ts.replace('Z','+00:00')) + timedelta(hours=8)`), or judge by "remote HEAD sha is newer than last known commit", never by "timestamp string starts with today's local date". Same trap hits any "is this commit newer than X" freshness logic against `gh api …/commits`.

**Pitfall 10 — direct-API (non-gh) push scripts must accept HTTP 201.** `POST git/blobs`, `git/trees`, `git/commits`, `git/refs` and a Contents `PUT` on create all return **201 Created**; the `gh` CLI masks this with exit 0, so a urllib/curl script that checks `status == 200` misjudges every create endpoint as a failure (observed: `ensure_repo` 404→POST returns 201 and a 200-only check raises "建仓失败 201" right after a successful repo create). Accept `(200, 201)`. Related: verify the FINAL url's host before blaming the network — a missing slash in `API_BASE + path` yields hosts like `api.github.comrepos/...` that fail with `getaddrinfo 11001`, identical symptoms to a real GFW DNS outage; a curl probe to the correct url succeeds while the script "retries" forever on the malformed one.

**Pitfall 11 — a single tree POST has a size ceiling: 422 "input too large".** Observed: a root tree POST of ~1050+ entries returns `422 "Sorry, your request timed out. It's likely that your input was too large... build the tree incrementally"`. It bites specifically on union-pushing against a remote whose tree is huge and flat (e.g. a prior push that landed ~1000 files at the root). Fallback: push the *local-only* tree (remote-unique files stay in git history, nothing is force-deleted), or restructure the remote side into sub-dirs and rebuild chunk-by-chunk.

**Pitfall 12 — Windows reserved device names break mirror trees.** A file literally named `nul` (any case of NUL/CON/PRN/AUX/COM\*/LPT\*) makes `os.path.relpath`/`os.walk`/zip/`git add` throw `ValueError: path is on mount '\\\\.\\nul'`. When mirroring an arbitrary local tree, filter these names case-insensitively and skip them (they are almost always `> NUL` accidents or junk — do not try to rename them into the upload).

**Pitfall 13 — the background-job PID is the shell wrapper's; verify death by command line, not by PID.** `terminal background=True` on this host reports the wrapper's pid; `taskkill /PID <wrapper>` kills the wrapper while the python child keeps running, writing to your log and still pushing. After killing a push job, confirm death with a command-line match (`wmic process where "name='python.exe'" get processid,commandline` or `tasklist` filtered on the script path) before starting a replacement — two writers on one repo race for the 5000/h rate budget and the stale, pre-fix writer can land a broken tree. Write per-repo log files, not one shared file, so interleaving cannot mask who wrote what.

**Deep recipe for large multi-repo pushes without the gh CLI (git-SHA1 blob dedup, union-against-existing-remote, rate-window planning, DNS pinning): `references/gh-api-push.md`.**

**Pitfall 14 — a blob POST that returns 400 "malformed request ... try resubmitting" is transient, not fatal.** GitHub's own message says resubmit: retry the same blob ≤5 times at ~10 s spacing before raising. A hard-fail on the first 400 aborts a whole multi-hundred-file repo push over one flaky upload; all other status codes still raise immediately.

**Pitfall 15 — repair a previously broken push by re-anchoring at the bad commit's `parents[0]`, never by deleting the repo.** If a landed tree turned out to be missing sub-branches (caught only by the recursive blob-count verify), fetch the bad main commit, read the tree of its `parents[0]` (the last good tree), union local files over that map, commit with `parents=[parent_sha]`, and update the ref with `force: true` once — allowed here because you are re-anchoring your own bad commit, forbidden on the recurring sync path (Pitfall / step 4). Remote-unique paths that the broken push dropped still exist in git history, so the parent-tree re-fetch recovers them; the force makes main point at a commit whose parent is the pre-break state, which a non-force update would reject as a rewind.

**Pitfall 16 — `git` reports `detected dubious ownership in repository` on a repo owned by an unmappable/old user SID (common after a Windows account migration), blocking `git ls-files`/commit locally.** Fix by whitelisting that repo: `git config --global --add safe.directory <repo-path>`. Two sub-traps: (a) if `safe.directory` **already has multiple values**, a single `git config --global safe.directory <path>` **fatals** with `cannot overwrite multiple values with a single value` — you MUST use `--add` (or `--replace-all`/regexp); (b) the ownership error is a **local git-ops** blocker only — adding to `safe.directory` unblocks the mirror/commit step but the actual GitHub push still needs a token, so don't expect the end-to-end job to go green from this fix alone.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `git push` asks for password | GitHub disabled password auth. Use a personal access token as the password, or switch to SSH |
| `remote: Permission to X denied` | Token may lack `repo` scope — regenerate with correct scopes |
| `fatal: Authentication failed` | Cached credentials may be stale — run `git credential reject` then re-authenticate |
| `ssh: connect to host github.com port 22: Connection refused` | Try SSH over HTTPS port: add `Host github.com` with `Port 443` and `Hostname ssh.github.com` to `~/.ssh/config` |
| Credentials not persisting | Check `git config --global credential.helper` — must be `store` or `cache` |
| Multiple GitHub accounts | Use SSH with different keys per host alias in `~/.ssh/config`, or per-repo credential URLs |
| `gh: command not found` + no sudo | Use git-only Method 1 above — no installation needed |
