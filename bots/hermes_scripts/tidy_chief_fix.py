#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B-fix: remove all orphan k10-N provider blocks from chief/config.yaml
(\r\n-safe). Default provider already switched to agnes-bot-chief (pool) by the
prior run; this just deletes the redundant k10-* apihub providers (nothing
references them). Validates YAML with Hermes's own venv yaml."""
import os, json, shutil

CFG = r"E:\workbuddy\国外模型\hermes\profiles\chief\config.yaml"
BAK = CFG + ".bak-k10fix-20261113"

def is_top(s):
    if not s.endswith(":"):
        return False
    if not s.startswith(" "):
        return True
    if s.startswith("  ") and not s.startswith("   "):
        return True
    return False

with open(CFG, encoding="utf-8") as f:
    lines = f.readlines()

# 1) ensure default provider is the pool (idempotent)
switched = False
step1 = []
for ln in lines:
    if ln.rstrip("\r\n") == "  provider: k10-6":
        step1.append("  provider: agnes-bot-chief\n")
        switched = True
    else:
        step1.append(ln)

# 2) remove k10-N provider blocks
final = []
i = 0
N = len(step1)
removed = 0
while i < N:
    s = step1[i].rstrip("\r\n")
    if s.startswith("  k10-") and s.endswith(":"):
        i += 1
        while i < N:
            s2 = step1[i].rstrip("\r\n")
            if is_top(s2):
                break
            i += 1
        removed += 1
        continue
    final.append(step1[i])
    i += 1

text = "".join(final)
shutil.copy2(CFG, BAK)
with open(CFG, "w", encoding="utf-8") as f:
    f.write(text)

valid = None
try:
    import yaml
    yaml.safe_load(text)
    valid = True
except Exception as exc:  # noqa: BLE001
    valid = f"{type(exc).__name__}: {exc}"

print(json.dumps({
    "default_switched_to_pool": switched,
    "k10_blocks_removed": removed,
    "backup": BAK,
    "yaml_valid": valid,
}, ensure_ascii=False))
