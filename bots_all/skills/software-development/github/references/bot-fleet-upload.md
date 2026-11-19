# Bot-fleet upload (bulk backup of a user's trading/automation bots to a repo)

## When to Use

When the user asks to back up or upload "all my bots" / the whole fleet
(cron wrapper trees + engine script trees, e.g. a trading system) to a
GitHub repo, or to make a bot fleet reconstructible from a single repo.

## Procedure

1. **Inventory first.** List every source tree (cron wrapper dir, engine
   root, scripts/, research/ ...). Count files and split by type: keep code
   (`.py`/`.ps1`/`.md`), exclude runtime junk (`__pycache__/`, `*.pid`,
   `DEVNULL`, `*_log.jsonl`, runtime logs, `data/`+cache/state dirs —
   state is not code; uploading it is diff noise and leaks runtime data).
2. **Credential scan BEFORE any copy** (mandatory, both trees + the cron
   jobs store): grep code files for `sk-[A-Za-z0-9]{16,}` ,
   `api_key\s*=\s*['"][^'"]{16,}` , `password\s*=\s*['"][^'"]{4,}` ,
   `BEGIN (RSA|EC|OPENSSH) PRIVATE` , `Bearer [A-Za-z0-9._-]{20,}`.
   Scan only code files in known dirs — whole-tree grep on huge trees
   times out. Triage hits: demo-account trading passwords → sanitize in step
   4; real API keys/tokens → STOP, exclude the file or confirm with the user
   before pushing. Never push a live API key.
3. **Copy into the repo layout**, one subdirectory per source tree (e.g.
   `bots/{wrappers,engine_root,engine_scripts,engine_research}/`), keeping
   the type filter from step 1.
4. **Sanitize copies only, never the live files** (the live scripts need
   the password to run; the repo copy documents an env-var contract
   instead): replace each password literal with
   `os.environ.get("<ENV_VAR>", "")`, then verify zero residue by re-grepping
   the repo tree for the literal. State the env-var names in a README note.
5. **Export the cron registry** so the fleet is reconstructible: parse the
   gateway jobs store (JSON) and emit a table (name, job_id, schedule,
   script-or-prompt-head, script-vs-agent mode, enabled, deliver) as both
   `.md` and `.json`. Agent-type jobs need the prompt head included, or
   they cannot be re-registered from the repo alone. Rebuild instruction =
   clone + register registry rows one by one.
6. **Commit + push with retry**: GitHub "Connection was reset" / "Could
   not connect" failures are transient — retry up to 3× with ~20s backoff
   before reporting failure. Verify success by remote HEAD == local commit
   (`git ls-remote` / `status -sb` showing no ahead), not by absence of
   error text.

## Pitfalls
- Sanitizing the LIVE scripts instead of the repo copies breaks running
  bots — the env-var substitution only belongs in the uploaded tree.
- A credential scan that times out is not a clean scan — restrict the
  search to code files in known directories and say so in the report.
- "All bots" without the cron registry is half a backup: scripts without
  their schedules cannot be rebuilt. Registry export is part of done, not
  optional.
- Excluding `data/`/cache dirs is deliberate: they are runtime state, not
  bot code; a 30MB npz cache in a public repo is both bloat and leakage.
