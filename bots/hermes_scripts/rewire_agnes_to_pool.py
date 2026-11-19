#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Batch-rewire Hermes profile configs: route Agnes CN provider traffic
(https://api.agnes-ai.cn) through the local key-pool proxy
(http://127.0.0.1:8787) for round-robin key load-balancing.

- Only rewrites the HOST portion, preserving the /v1 path and every other field.
- Leaves https://apihub.agnes-ai.com (a different upstream) untouched.
- Leaves key_env / api_key untouched (pool re-signs auth on its side).
- Backs up each touched file to config.yaml.bak-20261113 before editing.
"""
import os
import json

PROFILES = r"E:\workbuddy\国外模型\hermes\profiles"
OLD_HOST = "https://api.agnes-ai.cn"
NEW_HOST = "http://127.0.0.1:8787"
BAK_SUFFIX = ".bak-20261113"

# A profile config lives at profiles/<profile>/config.yaml
def iter_profile_configs():
    for profile in os.listdir(PROFILES):
        pdir = os.path.join(PROFILES, profile)
        if not os.path.isdir(pdir):
            continue
        cfg = os.path.join(pdir, "config.yaml")
        if os.path.isfile(cfg):
            yield cfg

def main():
    report = {"touched": [], "skipped_no_match": [], "error": []}
    for cfg in iter_profile_configs():
        try:
            with open(cfg, "r", encoding="utf-8") as f:
                text = f.read()
            if OLD_HOST not in text:
                report["skipped_no_match"].append(cfg)
                continue
            # backup (only if not already backed up)
            bak = cfg + BAK_SUFFIX
            backed = False
            if not os.path.exists(bak):
                with open(cfg, "r", encoding="utf-8") as f:
                    raw = f.read()
                with open(bak, "w", encoding="utf-8") as f:
                    f.write(raw)
                backed = True
            new_text, n = text.replace(OLD_HOST, NEW_HOST), text.count(OLD_HOST)
            with open(cfg, "w", encoding="utf-8") as f:
                f.write(new_text)
            report["touched"].append({
                "file": cfg,
                "replacements": n,
                "backup_created": backed,
                "backup_path": bak if backed else None,
            })
        except Exception as exc:
            report["error"].append({"file": cfg, "error": f"{type(exc).__name__}: {exc}"})
    # summary
    total_repl = sum(t["replacements"] for t in report["touched"])
    print(json.dumps({
        "configs_scanned": len(report["touched"]) + len(report["skipped_no_match"]) + len(report["error"]),
        "touched_files": len(report["touched"]),
        "total_replacements": total_repl,
        "skipped_no_match": len(report["skipped_no_match"]),
        "errors": len(report["error"]),
        "touched": report["touched"],
        "skipped_sample": report["skipped_no_match"][:10],
        "errors_detail": report["error"],
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
