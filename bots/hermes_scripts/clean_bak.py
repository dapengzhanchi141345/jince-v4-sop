#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A: Archive ALL *.bak* files under profiles into one zip, then delete the
originals. The zip is the safety net (full revert possible). Project-file
cleanup authorized by user 2026-11-13."""
import os, json, zipfile

PROFILES = r"E:\workbuddy\国外模型\hermes\profiles"
ARCHIVE = r"E:\workbuddy\国外模型\hermes\bak_archive_20261113.zip"

matches = []
for root, _dirs, files in os.walk(PROFILES):
    for f in files:
        if ".bak" in f:
            matches.append(os.path.join(root, f))
matches.sort()

with zipfile.ZipFile(ARCHIVE, "w", zipfile.ZIP_DEFLATED) as z:
    for p in matches:
        z.write(p, os.path.relpath(p, PROFILES))

deleted = 0
errors = []
for p in matches:
    try:
        os.remove(p)
        deleted += 1
    except Exception as exc:  # noqa: BLE001
        errors.append({"file": p, "error": str(exc)})

print(json.dumps({
    "found": len(matches),
    "archived_to": ARCHIVE,
    "deleted": deleted,
    "errors": errors,
}, ensure_ascii=False, indent=2))
