# Word delivery-report builder recipe (python-docx + matplotlib charts)

## When to Use
Step 3 of the benchmark→land→report loop: the user asked for a formal Word deliverable (封面/目录/彩色表格/图表/页码, 微软雅黑) summarizing a gap-analysis or landing batch. Also reach for it whenever any python-docx + matplotlib chart document build shows tofu glyphs, a color/bold arg swap, or a broken package.

Target output: cover page + TOC + color tables + embedded charts + page numbers, 微软雅黑, saved into the user's 交付 dir.

## Build steps (proven order)
1. Write a standalone builder script in scratch (`E:/workbuddy/国外模型/hermes/cache/scratch/build_*.py`); it generates the .docx by itself, so it stays re-runnable.
2. matplotlib chart FIRST (the builder embeds the PNG); python-docx body second. Save the docx, then validate the package: `zipfile.ZipFile(path).testzip() is None` + count `<w:tbl>`/`<pic:pic>` occurrences in `word/document.xml` — 0 issues, expected table/image counts = package ok.
3. Run with `env -u PYTHONPATH <project-venv>/.venv/Scripts/python.exe` — the host `PYTHONPATH` env var can point at a broken installs dir that pollutes the venv's PIL/matplotlib; unsetting it for the one command is the fix (already-installed deps: Pillow, python-docx, matplotlib).

## python-docx gotchas
- `run.font.color.rgb` needs an `RGBColor`, not a hex string — convert with `RGBColor.from_string(hex.lstrip("#"))`.
- 微软雅黑 on every run requires setting BOTH `font.name` and the East-Asia font: `r._element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")` (helper: `set_run`). Heading styles: re-assign the style THEN override the run props, or the theme font wins.
- Color table headers via `w:shd` fill on each `tcPr` (helper: shade_cell); zebra-stripe data rows the same way.
- Page numbers: append a `w:fldSimple` PAGE field to the section footer, bracketed by small gray runs.
- If a `P()` helper takes `(text, size, color, bold)` positionally, 4-arg call sites silently swap color↔bold — add an `isinstance(bold, str)` tolerance or make them keyword-only.

## matplotlib CJK tofu (recurring)
Default DejaVu renders CJK as boxes. Before plotting, scan `matplotlib.font_manager` for a CJK face and set it:
```python
import matplotlib.font_manager as fm
for f in ["Microsoft YaHei", "SimHei"]:
    if any(f.lower() in t.name.lower() for t in fm.fontManager.ttflist):
        plt.rcParams["font.sans-serif"] = [f, "DejaVu Sans"]; break
plt.rcParams["axes.unicode_minus"] = False
```
Watch the build output for `Glyph ... missing from font` warnings — that IS the tofu detector; re-run after the font fix and confirm zero warnings before delivering.

## Chart shapes that work in these reports
- 8-row status bar chart (horizontal bars, labeled 已落地/未做) for panel-landing status.
- Radar chart for multi-dimension capability comparison (keep tick labels count == tick positions count, or matplotlib throws).
