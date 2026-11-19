# CJK python-pptx deck toolkit

For custom CJK multi-card decks the JSON-spec `pptx_create.py` can't express. Keep one build script as the source of truth; run it after every content edit.

## Base setup

```python
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.ns import qn

prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)  # 16:9
BLANK = prs.slide_layouts[6]   # blank; index varies per template — confirm via outline's layouts_available
```

Dark + gold house palette: BG `0E1420`, card `1A2334` / `222E44`, gold `D4AF37`, accent blue `4FC3F7`, body text `E8E6E1`, muted `9AA5B8`, warning red `E05B4B`, good green `5FBF7A`.

## East-Asian font helper (call on EVERY run)

`run.font.name = "微软雅黑"` writes only the Latin typeface; PowerPoint renders CJK via `a:ea` and falls back to a default font without it.

```python
def _set_font(run, name="微软雅黑"):
    run.font.name = name
    rPr = run._r.get_or_add_rPr()
    ea = rPr.find(qn('a:ea'))
    if ea is None:
        ea = rPr.makeelement(qn('a:ea'), {})
        rPr.append(ea)
    ea.set('typeface', name)
```

## Card + text helpers (cover ~90% of visual needs)

- Card: `MSO_SHAPE.ROUNDED_RECTANGLE`, `fill.solid()`, `line.fill.background()`, `shadow.inherit = False`; content goes in the shape's `text_frame` as multiple paragraphs. A single `add_card(slide, x, y, w, h, lines=[(text, size_pt, color, bold, space_after), ...])` helper covers most layouts.
- Connectors: `MSO_SHAPE.RIGHT_ARROW` / `DOWN_ARROW` with solid fill between cards.
- Text: `add_textbox` with `tf.word_wrap = True`, zero margins, one paragraph per line, `p.line_spacing` for CJK comfort.
- Tables: `slide.shapes.add_table(...)` then style every cell (`fill.solid()`, `vertical_anchor = MSO_ANCHOR.MIDDLE`, margins) — default table styling is ugly on dark backgrounds. Header row: dark-gold fill `8A6D1F` + dark text; body rows alternate card fills.
- Footer / page number: plain textboxes per slide (placeholder copying is unreliable on blank layouts).

### Multi-paragraph shape for dense methodology / template slides

For slides that hold "copyable templates" (prompt blocks, code snippets, step lists where each line has its own font/color/bold), the single `add_card(lines=[...])` is too rigid. Add two helpers to the shared `Deck` class:

```python
def add_card_lines(self, s, x, y, w, h, fill=CARD, lines=None, align=PP_ALIGN.LEFT,
                   anchor=MSO_ANCHOR.MIDDLE, radius=None, border=None, border_w=1.25,
                   line_spacing=1.05, space_after=3):
    # create rounded-rect shape (fill/border/shadow.inherit=False), then:
    tf = shp.text_frame; tf.word_wrap = True; tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Inches(0.14); tf.margin_top = tf.margin_bottom = Inches(0.08)
    tf._line_spacing = line_spacing; tf._space_after = space_after
    if lines: self.add_lines(shp, lines)
    return shp

def add_lines(self, shp, lines):
    """lines: [(text, size, color, bold, italic?, mono?, space_after?), ...]"""
    tf = shp.text_frame; ls = getattr(tf, '_line_spacing', 1.05); sa = getattr(tf, '_space_after', 3)
    for i, item in enumerate(lines):
        text, size, color, bold, *rest = item
        italic = rest[0] if len(rest) > 0 else False
        mono   = rest[1] if len(rest) > 1 else False
        space  = rest[2] if len(rest) > 2 else sa
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.LEFT; p.space_after = Pt(space); p.line_spacing = ls
        r = p.add_run(); r.text = text; r.font.size = Pt(size); r.font.color.rgb = color
        r.font.bold = bold; r.font.italic = italic
        if mono:
            r.font.name = 'Consolas'
            rPr = r._r.get_or_add_rPr(); ea = rPr.find(qn('a:ea'))
            if ea is None: ea = rPr.makeelement(qn('a:ea'), {}); rPr.append(ea)
            ea.set('typeface', 'Consolas')   # mono CJK still needs a:ea or it falls back
        else:
            _set_font(r)
```

Set `mono=True` for code/prompt lines; leave `False` for prose. A subtle bug: writing `r.font.name = 'Consolas'` alone sets the Latin typeface only — the `a:ea` must also be set to Consolas or CJK inside a mono line silently falls back to a default font.

## Speaker notes in the build script

`slide.notes_slide.notes_text_frame.text = "..."` — author notes while building (per-slide, as a talk track the user will say live), not by post-processing the file with `--set-notes`.

## Multi-part build for 40+ slide decks

When a deck exceeds ~30 slides, split the build into several files that each export a `build(d)` function feeding one shared `Deck` instance:

```
decklib.py            # shared: Deck class, palette, _set_font, add_card / add_card_lines / add_lines / make_table
build_deck_b1.py      # part 1 (defines build(d))
build_deck_b2.py      # part 2 (defines build(d))
build_deck_b3.py      # part 3 (defines build(d))
build_deck_b.py       # orchestrator: create Deck, call build(d) from b1/b2/b3 in order, set all NOTES, d.save()
```

Rules:
- All slide creation happens INSIDE `build(d)` so slide numbering stays deterministic and renumbering is contained.
- The orchestrator creates one `Deck`, calls each part's `build(d)` in order, then writes the full `NOTES` dict (1-based, matching final slide order) and `d.save()`.
- To insert a new section: add `build_deck_b4.py`, import it, call `build(d)` in order, then renumber the tail of NOTES. Never reorder slides by editing a part file's internals.
- **Inserting ANY page mid-deck shifts everything after it**: the `NOTES` dict is 1-based and keyed to final slide order, so inserting page K renumbers NOTES keys K+1..N, AND every hardcoded cross-reference in body copy ("本合成文件第 20–67 页", "见 P45", "下篇第 N–M 页") goes stale and must be re-synced by the same delta. Treat "insert a slide" as a whole-deck renumber, not a local edit — grep the build scripts for `第 .*页` / page-range strings and fix them in the same pass. Cheaper: keep cross-references generic ("下篇 / 后半部分") when the exact page number will drift as the deck grows.
- Keep `decklib.py` in the build folder so `import decklib` works when running the orchestrator from that dir.

## Verification without LibreOffice

1. `pptx_read.py OUT.pptx --outline > outline.json` (run the CLI directly in the terminal, redirect to file); inspect with `json.load(open(..., encoding="utf-8"))`.
2. Tables in that JSON are nested `[[cell, ...], ...]` lists — iterate rows, do NOT index a `rows` key.
3. Leak scan: join all texts + table cells into one string; grep for forbidden tokens (org names, credentials, absolute internal paths) and confirm required ones (presenter name only as name, disclaimer, user node labeled 客户/决策者).
4. Rebuild after every edit; never hand-edit the .pptx.

## Windows/MSYS gotchas

- MSYS path conversion is disabled for native tools: pass `C:/...` forward-slash paths to python; inside the Python source use forward slashes (MSYS-style `/c/...` breaks `os.path` into `C:/...`).
- Non-ASCII JSON through pipes/`head`/`subprocess` capture gets mangled or truncated — redirect to a file and read it.
- `exec_module` on the skill scripts is fragile (module-level code can swallow stdout); prefer plain CLI invocation.

## Merging / reordering two built decks (OOXML level)

For combined deliveries ("合成一个交付" / "把 X 放前边"). PowerPoint COM copy/paste is flaky in headless use — do it on raw zip:

1. Base on deck A. Copy B's parts into A's namespace with an OFFSET: B's `slide1..48` become `slide21..68` (= `slide{N_A + k}`, 0-based k, N_A = A's slide count), and rewrite B's internal rel targets to match (`ppt/slides/_rels/slideN.xml.rels` → notesSlide target; `ppt/notesSlides/_rels` likewise).
2. `[Content_Types].xml`: add B's slide/notesSlide Override entries; if any A slide is dropped (e.g. a mid-deck 谢谢聆听 page), also REMOVE its Override and do NOT copy its part.
3. `ppt/_rels/presentation.xml.rels`: add one Relationship per B slide with rIds continuing after the existing max; remove the Relationship of any dropped A slide.
4. `ppt/presentation.xml`: rebuild `<p:sldIdLst>` as A's kept slides + B's slides in the desired presentation order; sldId values must exceed the existing max, r:id points at the new relationships.
5. Verify NO duplicate part names: `collections.Counter(zipfile.ZipFile(out).namelist())` — any count > 1 means the deck will open with repair prompts. Python's `zipfile` silently writes two entries of the same name (last one wins on read), so a collision at an offset boundary (e.g. B's slide k=20 landing on A's dropped `slide20.xml`) corrupts the file without any error.
6. Reordering = sldIdLst order only; physical parts may stay where they are. An optional python-pptx open+save normalizes physical names to 1..N — then re-verify sldIdLst order AND part-name uniqueness.
7. Renumber footers: footers are per-slide plain textboxes (see house spec), so after any reorder, sweep every slide and rewrite footer numbers to 01..N in the NEW position order.
8. Re-run the leak scan + full per-page render QA on the merged file, not just its inputs.

Pitfalls:
- Dropping one A slide costs three removals: its zip part, its Content_Types Override, and its presentation.xml.rels Relationship — miss any one and PowerPoint may fail to open or repair-prompt.
- Stale PowerPoint lock: when a COM render open fails after earlier COM use, `taskkill /F /IM POWERPNT.EXE`, remove `~$*.pptx` lock files, then retry before concluding COM is broken.
