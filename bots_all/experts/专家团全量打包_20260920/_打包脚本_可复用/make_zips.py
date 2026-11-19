# -*- coding: utf-8 -*-
"""打包专家团核心包 + 依赖技能包。"""
import os, sys, time, zipfile

BASE = r"E:\workbuddy\专家团\专家团全量打包_20260920"
MARKET = r"C:\Users\ASUS\.workbuddy\plugins\marketplaces\my-experts"
SKILLS = r"C:\Users\ASUS\.workbuddy\skills"

DEP_SKILLS = [
    "calc-bazi",
    "teaching-visualization",
    "agnes-ai-support",
    "physics-grader-workflow",
    "exam-grading-workflow",
    "it-courseware-optimize",
    "pptx-zh-courseware",
]

EXCLUDE_DIRS = {"__pycache__", ".git", ".DS_Store", "node_modules", ".venv", "venv"}
EXCLUDE_FILES = {".DS_Store", "Thumbs.db", ".agnes-key"}


def is_excluded(rel):
    parts = rel.replace("\\", "/").split("/")
    if any(p in EXCLUDE_DIRS for p in parts):
        return True
    if parts[-1] in EXCLUDE_FILES:
        return True
    return False


def walk_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            if fn in EXCLUDE_FILES:
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root)
            if is_excluded(rel):
                continue
            yield full, rel


def zip_dir(root, arc_prefix, out_zip, label, compresslevel=6):
    t0 = time.time()
    n = 0
    total = 0
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=compresslevel, allowZip64=True) as z:
        for full, rel in walk_files(root):
            arc = f"{arc_prefix}/{rel}".replace("\\", "/") if arc_prefix else rel.replace("\\", "/")
            z.write(full, arc)
            n += 1
            total += os.path.getsize(full)
    size = os.path.getsize(out_zip)
    print(f"[OK] {label}\n     文件 {n} 个 | 原始 {total/1048576:.1f}MB -> 压缩 {size/1048576:.1f}MB | 耗时 {time.time()-t0:.1f}s")
    return size


if __name__ == "__main__":
    print("=== 打包 01 专家团核心包 ===", flush=True)
    zip_dir(MARKET, "my-experts",
            os.path.join(BASE, "01_专家团核心包_my-experts.zip"), "01_专家团核心包_my-experts.zip")

    print("\n=== 打包 02 依赖技能包 ===", flush=True)
    out = os.path.join(BASE, "02_依赖技能包_dependency-skills.zip")
    n = 0
    total = 0
    t0 = time.time()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as z:
        for s in DEP_SKILLS:
            p = os.path.join(SKILLS, s)
            if not os.path.isdir(p):
                print(f"  [SKIP] 不存在: {s}")
                continue
            for full, rel in walk_files(p):
                z.write(full, f"{s}/{rel}".replace("\\", "/"))
                n += 1
                total += os.path.getsize(full)
    print(f"[OK] 02_依赖技能包_dependency-skills.zip\n     文件 {n} 个 | 原始 {total/1048576:.2f}MB -> 压缩 {os.path.getsize(out)/1048576:.2f}MB | 耗时 {time.time()-t0:.1f}s")
