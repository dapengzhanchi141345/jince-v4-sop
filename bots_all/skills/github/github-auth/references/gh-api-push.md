# Git Data API bulk push (no gh CLI) — scaling recipe

## When to Use
- This host's `github.com:443` is GFW-walled but `api.github.com` resolves via DoH, the `gh` CLI is not installed, and the task is a multi-repo or large-tree push (hundreds to thousands of blobs, possibly across rate windows).
- Re-pushing or union-updating a repo that already has remote content (skip already-uploaded blobs instead of re-uploading).
- Push is done with stdlib `urllib` + a classic PAT (`repo` scope; the user supplies it; it is never committed into any repo and stored only in a scratch path).

SKILL.md carries the minimal one-repo recipe and Pitfalls 1-13; this file is the multi-repo / large-tree playbook.

## 0. Rate-window budget
- A PAT gives ~5000 core requests/hour; each blob upload is one call. Plan large payloads across windows: a ~7000-file tree needs ~2 windows. The script must read `X-RateLimit-Remaining` / `X-RateLimit-Reset` on every response and, at ~15 remaining, `sleep(until reset + 15s)` and resume — never crash, because the blob cache (below) makes resumption free.
- Run the whole push in the background (SKILL.md Pitfall 8); a 30-min tool timeout that kills it just costs one resume.

## 1. git-SHA1 blob dedup — skip uploads even on first push
- A git blob sha is computable locally with stdlib `hashlib` (no git binary): `sha1(b"blob %d\0" % len(data) + data)` over the file bytes.
- For a repo that already has content: fetch `GET repos/O/R/git/trees/<ref>?recursive=1`, build `{blob_sha: path}`, and reference the remote sha directly for every local file whose computed blob sha is in that set. Re-pushes and union pushes then upload almost nothing (observed: hundreds of blobs satisfied with zero uploads).
- Persist a JSON cache keyed `{repo}:{blob_sha}` → uploaded blob sha (or the remote sha you referenced), so a killed process resumes without re-uploading; also keep a per-repo completion ledger so a re-run skips finished repos.

## 2. Union push against an existing remote (add/refresh, never prune)
- A commit built from local-only content deletes every remote path missing from the tree (SKILL.md Pitfall 7). Add/refresh semantics: base = the remote tree's entries, overlay local files (local wins per path), `parents` = current remote HEAD, non-force.
- After you accidentally push a broken commit: re-anchor with `force=true` ONCE, using the broken commit's `parents[0]` tree as base (never the broken head's tree), so remote-unique files survive. A recurring sync never forces.
- If the union tree exceeds the single-POST ceiling (SKILL.md Pitfall 11), fall back to a local-only tree push; remote-unique content remains reachable in git history.

## 3. Tree building
- Bottom-up by level (root depth -1, then 0, 1, ...); register every intermediate directory at its own level — off-by-one silently drops whole sub-branches while all POSTs return 201 (SKILL.md Pitfall 3).
- Verify with `GET trees/<new-sha>?recursive=1`: blob count must equal the local file count (adjust for a seeded README). A shortfall means missing parent→child dir references; fix the tree entries, do not re-upload blobs.

## 4. Empty-repo seeding
- Unlock via Contents API seed (SKILL.md Pitfall 1). Provisioning can take 60+ minutes: re-probe from fresh processes, never delete+recreate, run a bounded watchdog loop (e.g. 60 × 45s) and keep the payload mirrored locally so nothing is lost while waiting. An interactive session reports the handoff state and moves on instead of blocking.

## 5. Network-flake crutches (re-validate before concluding 'down')
- GFW interference on api.github.com shows up as intermittent `getaddrinfo` failures (Errno 11001) while curl to the right host succeeds. Mitigations that worked: pin a DoH-resolved IP for `api.github.com` (AliDNS `223.5.5.5/resolve?name=...&type=A` or Cloudflare `1.1.1.1/dns-query`), round-robin across pinned IPs on failure, re-resolve periodically, and retry each request with backoff. Treat any single failure as retry, and re-probe before reporting a wall.
- One writer per repo, per-repo log files (SKILL.md Pitfall 13): duplicate background jobs on the same repo burn the shared rate budget and interleave log lines so failures are misattributed.
