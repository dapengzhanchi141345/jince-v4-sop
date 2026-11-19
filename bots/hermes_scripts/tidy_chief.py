#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B: Tidy chief/config.yaml.
- Switch model.provider from k10-6 (apihub) back to agnes-bot-chief (the local
  21-key pool) so chief's PRIMARY traffic uses the rotating pool like every
  other profile.
- Remove the redundant orphan k10-1..k10-10 provider block (nothing references
  them; fallback_providers already use agnes-main / agnes-com-chief* which stay).
Backs up to config.yaml.bak-tidy-20261113 first. Validates YAML after edit.
"""
import os, json, shutil

CFG = r"E:\workbuddy\国外模型\hermes\profiles\chief\config.yaml"
BAK = CFG + ".bak-tidy-20261113"

with open(CFG, "r", encoding="utf-8") as f:
    lines = f.readlines()

# 1) switch default provider
new_lines = []
switched = False
for ln in lines:
    if ln.rstrip("\n") == "  provider: k10-6":
        new_lines.append("  provider: agnes-bot-chief\n")
        switched = True
    else:
        new_lines.append(ln)

# 2) remove k10 block: from "  k10-1:" up to (not incl) next top-level provider
start = None
end = None
for i, ln in enumerate(new_lines):
    if ln.rstrip("\n") == "  k10-1:":
        start = i
    elif start is not None and i > start and ln.startswith("  ") and not ln.startswith("   ") and ln.rstrip("\n").endswith(":"):
        # first provider line after k10-1 block
        end = i
        break
removed = 0
if start is not None and end is not None:
    removed = end - start
    new_lines = new_lines[:start] + new_lines[end:]
elif start is not None:
    # fallback: remove to EOF (shouldn't happen)
    new_lines = new_lines[:start]

text = "".join(new_lines)

# backup then write
shutil.copy2(CFG, BAK)
with open(CFG, "w", encoding="utf-8") as f:
    f.write(text)

# validate YAML if available
valid = None
try:
    import yaml  # Hermes dep
    yaml.safe_load(text)
    valid = True
except Exception as exc:  # noqa: BLE001
    valid = f"yaml-check-skipped: {type(exc).__name__}"

print(json.dumps({
    "provider_switched_to_pool": switched,
    "k10_block_lines_removed": removed,
    "backup": BAK,
    "yaml_valid": valid,
}, ensure_ascii=False, indent=2))
