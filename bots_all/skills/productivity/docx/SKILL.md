---
name: docx
description: Create, read, edit, template, and review Word .docx files.
version: 1.1.0
author: Nous Research
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [word, docx, documents, office, templates, revisions, comments]
    category: productivity
    related_skills: [pdf, xlsx, powerpoint]
---

# Docx Skill

Create, read, edit, and template Microsoft Word `.docx` files with
python-docx via small CLIs. It handles text, styles, lists, tables,
images, headers/footers, `{{token}}` templating, tracked changes
(list/accept/reject), comments (list/add/delete), TOC and page-number
fields, and package health checks. It does not render documents itself
(PDF needs LibreOffice — see Converting to PDF) or edit legacy `.doc`.

## When to Use

- The user asks to generate a Word document (report, letter, contract).
- You need the text, outline, styles, or embedded images of a `.docx`.
- You must change an existing `.docx`: replace text, edit table cells,
  insert/delete paragraphs, apply styles, merge fragmented runs.
- You have a `.docx` template with `{{placeholders}}` to fill from data.
- The document has tracked changes to review, accept, or reject.
- You need to read reviewers' comments, or add/delete comments.
- A `.docx` won't open or behaves oddly and you need corruption triage.
- The document needs a table of contents or "Page X of Y" footers.
- Not for: `.doc` (legacy), `.odt`, or WYSIWYG layout work.

## Prerequisites

- Python 3.10+ with `python-docx` installed:
  `pip install python-docx` (import name is `docx`; lxml comes with it).
- Comments `add` uses the native API on python-docx >= 1.2 and an XML
  fallback on older versions — both are automatic.
- For image blocks: the image files must exist locally (PNG/JPEG).

## How to Run

All helpers live in `scripts/` next to this file. Run them with the
`terminal` tool; each supports `--help` and prints JSON to stdout.

```bash
python scripts/docx_create.py spec.json out.docx
python scripts/docx_read.py out.docx --text
python scripts/docx_edit.py replace out.docx --find old --replace new
python scripts/docx_template.py tpl.docx values.json filled.docx
python scripts/docx_revisions.py list out.docx
python scripts/docx_comments.py list out.docx
python scripts/docx_validate.py out.docx
```

## Quick Reference

| Task | Command |
| --- | --- |
| Create from JSON spec | `docx_create.py spec.json out.docx` |
| Full text (body+tables+headers/footers) | `docx_read.py f.docx --text` |
| Heading outline + table shapes | `docx_read.py f.docx --structure` |
| Styles actually used | `docx_read.py f.docx --styles` |
| Extract embedded images | `docx_read.py f.docx --images outdir/` |
| Detect tracked changes/comments | `docx_read.py f.docx --revisions` |
| Find/replace (formatting kept) | `docx_edit.py replace f.docx --find A --replace B -o out.docx` |
| Set a table cell | `docx_edit.py set-cell f.docx --table 0 --row 1 --col 2 --text X` |
| Insert paragraph before index N | `docx_edit.py insert f.docx --index N --text X --style Normal` |
| Delete paragraph N | `docx_edit.py delete f.docx --index N` |
| Apply style to paragraph N | `docx_edit.py style f.docx --index N --style "Heading 1"` |
| Merge equal-format adjacent runs | `docx_edit.py normalize f.docx -o out.docx` |
| Insert TOC field before para N | `docx_edit.py toc f.docx --index N -o out.docx` |
| "Page X of Y" footer fields | `docx_edit.py page-numbers f.docx` |
| Fill `{{tokens}}` | `docx_template.py tpl.docx values.json out.docx --strict` |
| List revisions (id/author/date/text) | `docx_revisions.py list f.docx` |
| Accept / reject all revisions | `docx_revisions.py accept-all f.docx -o out.docx` (or `reject-all`) |
| Accept / reject one revision | `docx_revisions.py accept f.docx --id 3 -o out.docx` |
| List comments (+anchored text) | `docx_comments.py list f.docx` |
| Add comment anchored to text | `docx_comments.py add f.docx --target "phrase" --text "note" --author You` |
| Delete comment by id | `docx_comments.py delete f.docx --id 0` |
| Health-check the package | `docx_validate.py f.docx` (exit 1 on errors) |

## Procedure

1. **Create.** Write a JSON spec with `write_file`, then run
   `scripts/docx_create.py`. The spec supports: `page` (size + margins in
   mm), `header`/`footer` strings, `footer_page_numbers` (adds a
     "Page X of Y" field footer), `styles` (LIST of custom paragraph style
     objects, each `{"name", "font", "size", "bold", "color"}` — `color`
     is bare hex without `#`; avoid built-in names like `Title`), and
     `blocks` — `heading`
   (level 1-9), `paragraph` (either `text` or a `runs` list where each run
   may set `bold`/`italic`/`underline`), `bullet_list`, `numbered_list`,
   `table` (`header` row rendered bold, `rows`, optional built-in table
   `style` such as `Table Grid`), `image` (`path`, optional `width_mm`),
   `toc` (Table of Contents field), and `page_break`. The full spec
   format is documented at the top of `scripts/docx_create.py`.
2. **Read.** Use `scripts/docx_read.py` with exactly one mode flag.
   `--text` returns body paragraphs, all table cell text, and
   header/footer text as JSON. `--structure` returns the heading outline
   plus paragraph/table/section counts. `--images DIR` copies every file
   under `word/media/` out of the package.
3. **Edit.** Use `scripts/docx_edit.py`. `replace` walks body, tables
   (nested included), headers and footers, and preserves run formatting;
   add `--body-only` to skip headers/footers. Pass `-o out.docx` to keep
   the original; omit it to edit in place. Paragraph indices for
   `insert`/`delete`/`style`/`toc` refer to `--structure`/`--text` body
   order. Run `normalize` first on documents that came out of heavy Word
   editing — it merges adjacent runs with identical formatting so later
   find-replace matches reliably.
4. **Review revisions.** `docx_revisions.py list` reports every `w:ins`
   and `w:del` (id, author, date, affected text) anywhere in body,
   tables, headers, or footers. `accept-all` / `reject-all` resolve them
   in bulk; `accept`/`reject --id N` handles a single revision. Accept
   keeps insertions and drops deleted text; reject does the reverse.
5. **Comments.** `docx_comments.py list` returns each comment's id,
   author, date, body text, and the document text it is anchored to.
   `add --target "some phrase"` anchors a new comment to the first
   occurrence of that phrase (runs are split as needed; formatting is
   preserved). `delete --id N` removes the comment and its markers
   without touching document text.
6. **Template.** Put `{{name}}`-style tokens in the document. Run
   `scripts/docx_template.py` with a JSON object of values. Use
   `--strict` to fail when tokens remain unfilled; the JSON output lists
   `filled` counts and `unfilled_tokens` either way.
7. **Verify** (always): re-read the output with `--text` or
   `--structure`, and run `docx_validate.py` on anything you produced
   via revision/comment surgery.

## Converting to PDF

No script needed. When LibreOffice is installed, convert headlessly:

```bash
soffice --headless --convert-to pdf --outdir outdir/ file.docx
```

Check availability first (`command -v soffice || command -v
libreoffice`). If neither exists, tell the user PDF conversion is
unavailable in this environment rather than improvising — python-docx
cannot render PDFs, and layout fidelity requires a real renderer.

## Pitfalls

- **Tokens split across runs.** Word often fragments text into several
  runs. The replace helpers collapse matched runs (replacement inherits
  the first run's formatting); running `docx_edit.py normalize` first
  reduces fragmentation for all later edits.
- **Revision coverage.** `docx_revisions.py` resolves run-level
  insertions and deletions (the overwhelming majority). Paragraph-mark
  and table-row revisions, format-change records, and moves are detected
  by `--revisions` but not auto-resolved — see
  `references/revisions-and-comments.md` and hand those to Word.
- **Comment threading.** Replies and "resolved" status live in
  `commentsExtended.xml`, which this skill ignores; comments it adds are
  plain top-level comments.
- **Field results are computed by Word.** `toc`, `page-numbers`, and the
  `toc`/`footer_page_numbers` spec options write *field codes*.
  Word/LibreOffice populates the actual entries and numbers when the
  file is opened (Word may prompt to update fields); python-docx never
  computes them, so placeholder text shows until then.
- **Validation is a health check, not schema validation.**
  `docx_validate.py` verifies the zip, required parts, relationship
  targets, image magic bytes, and referenced styles. It is NOT XSD
  validation — a file can pass and still contain XML Word dislikes.
- **Style names must exist.** Applying a style that isn't defined in the
  document raises `KeyError`. Built-ins like `Heading 1`, `List Bullet`,
  `List Number`, `Table Grid` exist in the default template; custom
  styles must be declared in the create spec first.
- **docx_create.py spec `styles` pitfalls (three, each hit once in practice).**
  ① `styles` is a LIST of objects each carrying `"name"` — a dict keyed
  by style name (e.g. `{"Title": {...}}`) crashes with
  `TypeError: string indices must be integers` because the script does
  `s["name"]`.  ② Each style's `color` must be a bare 6-hex WITHOUT `#`
  (`RGBColor.from_string('#1F4E79')` raises `invalid literal for int()
  with base 16: '#1'`). ③ Custom style names must not collide with
  python-docx built-ins — the default template already defines `Title`,
  so `add_style('Title')` raises `document already contains style
  'Title'`; prefix custom names (e.g. `RPTTitle`/`RPTBody`). ④ Each
  block dict in `blocks` carries its block type under the key **`type`**
  (e.g. `{"type": "table", "header": [...], "rows": [...]}`) — naming it
  `kind` crashes with `KeyError: 'type'` (the spec doc at the top of the
  script says "type"; it is easy to write `kind` from habit). Verify
  with `docx_read.py --structure` (heading outline + table shapes) and
  `docx_validate.py` after each create.
- **Numbered lists restart.** `List Number` relies on Word's default
  numbering; separate lists in one document may continue numbering
  instead of restarting. Warn users needing precise multi-list numbering.
- **Cell writes replace formatting.** `set-cell` uses `cell.text = ...`,
  which resets runs in that cell to plain formatting.
- **Encoding.** All JSON specs/values files are read as UTF-8 explicitly;
  never rely on locale defaults when writing your own glue code.
- **Chinese docs: set eastAsia font on every run.** `font.name = '微软雅黑'` only sets the latin font; CJK glyphs keep the theme default. Wrap every run/style: `r._element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')` (styles via `style.element.rPr.rFonts`); also `axes.unicode_minus=False` + `font_manager.fontManager.addfont(r'C:\Windows\Fonts\msyh.ttc')` for any embedded matplotlib charts, or labels render as tofu boxes. Shortcut: when matplotlib's font cache already resolves the system font, `rcParams['font.sans-serif']=['Microsoft YaHei']` alone suffices — reserve addfont for hosts where the cache doesn't see system fonts.
- **Large specs: build with Python, not a giant JSON.** A data-dense report spec (cover + TOC + many CJK tables + images) easily exceeds the streaming limit and trips `write_file`'s JSON syntax validation (one stray trailing comma aborts the whole write). When the spec would be >~15KB, write small Python builder scripts (python-docx directly, split in two passing an intermediate `.docx`); still finish with `docx_validate.py` + `docx_read.py --structure`.
  - **Custom-builder pitfalls (data-dense Chinese report builders that use python-docx directly):**
    - `run.font.color.rgb` only accepts an `RGBColor` object, not a hex string (`'#1F4E79'` raises `ValueError: rgb color value must be RGBColor object`). Normalize in one helper: `if isinstance(color, str): color = RGBColor.from_string(color.lstrip('#'))`.
    - For a Word-navigation-pane outline (and non-empty `--structure` output), set headings via `doc.add_heading(text, level=1)` and then restyle the runs — `add_paragraph()` + colored runs produces visually-identical headings but an **empty outline**, which users read as "not a real document".
    - matplotlib `set_xticks(n_positions)` and `set_xticklabels(n_labels)` MUST have equal counts or the figure raises `ValueError: The number of FixedLocator locations does not match the number of labels`.
    - In this host's git-bash, `PYTHONPATH` can point at a broken `installs/` site-packages directory (contaminated PIL/mpl imports). Run builders with `env -u PYTHONPATH <project>.venv/Scripts/python.exe ...` and install `python-docx` + `matplotlib` + `Pillow` + `pyparsing` + `kiwisolver` + `python-dateutil` into the **project's own** venv — a bare `import PIL` may "succeed" against the polluted global path and fail the moment PYTHONPATH is cleared.
    - A module docstring that embeds backslashed Windows paths (C:\Users\...) in the builder .py triggers `SyntaxError: (unicode error) 'unicodeescape' ... truncated \UXXXXXXXX escape` on the first backslash (`\U` in `\Users`), and it only surfaces at build time, not in the editor. Write that docstring as a raw string `r"""..."""` (or double the backslashes).
    - A hex color string that lands in a run-helper's boolean slot (arg-order slip, `P(text, 10.5, GREEN, True)` instead of `P(text, 10.5, True, GREEN)`) fails late at `doc.save()` with `TypeError: only True or False (and possibly None) may be assigned, got '#2E7D32'`. Guard the helper so both orderings work: `if isinstance(bold, str): color, bold = bold, False`.
    - Nested double quotes inside CJK string literals are a silent build-time landmine: Chinese text like `跑通"信号→风控→执行"全链路` contains characters (`→`, `、`) that are valid text but break the .py the moment the inner `"` closes the literal early — you then spend the session doing regex surgery on the builder itself, corrupting it further. Write all such inner quotes as CJK corner brackets 「…」 while authoring the builder, never as `"`. Never patch a damaged builder with regex quote-swap passes: each pass mangles legitimate string delimiters; rewrite the whole builder script cleanly instead.
    - Syntax-check every builder .py with `py_compile.compile(path, doraise=True)` BEFORE running it (and after every edit), because docstring/string errors only surface at build time, not in the editor.
    - Known-good host venv for these builders (python-docx + matplotlib + Pillow preinstalled): `D:/jince_sass/.venv/Scripts/python.exe` — check `import docx` there before falling back to the Hermes tools python. `D:/workbuddy/binaries/python/versions/3.13.12/python.exe` also works: `python -m pip install python-docx matplotlib` succeeds there (verified 11-11) — third known-good runner when the two venvs are absent.
    - Raw field XML in a custom builder (TOC / PAGE / NUMPAGES): `CT_P` has no `get_or_add_r()` — `p._p.get_or_add_r()` raises `AttributeError` at build time. Append the `w:fldChar`/`w:instrText`/`w:t` elements to a RUN element instead: `r = p.add_run(); r._element.append(fldChar_begin); r._element.append(instrText); r._element.append(fldChar_end)` in the begin→instrText→separate→placeholder→end order; one run per element.
    - **`qn()` returns a tag STRING, never an element — appending it directly is a `TypeError: Argument 'element' has incorrect type` at build time.** Every raw-XML append (fldChar/instrText, `w:shd` cell shading, any custom child) must build a fresh element via `parent_el.makeelement(qn(tag), {qn(attr): val})` then `.append(el)` — e.g. cell shading: `tcpr = cell._tc.get_or_add_tcPr(); tcpr.append(tcpr.makeelement(qn('w:shd'), {qn('w:val'):'clear', qn('w:fill'):'1F3A5F'}))`. White-on-colored header text needs the fill set on the same pass or the white text is invisible.
    - **There is no `doc.last_paragraph`** (AttributeError); use `doc.paragraphs[-1]` after `add_picture` if you need to center the just-inserted image paragraph.
    - matplotlib chart glyphs: msyh (msyh.ttc) lacks decorative marks — ✓ (U+2713), ⚠, − render as tofu boxes in the embedded PNG even with `font_manager.addfont` done right; write chart labels as CJK words (「已成交」, 「警示」) instead of unicode marks. A missing-glyph `UserWarning: Glyph NNNNN missing from font` at `savefig` time is the tell.
    - **Hex-color convention flips between the two libraries in one builder**: python-docx wants bare hex without `#` (`RGBColor.from_string('1F3A5F')`), matplotlib wants `#`-prefixed (`color='#1F3A5F'`). A shared color constant must be prefixed per call (`'#' + NAVY`); otherwise `bar`/`axvline`/`ax.text(color=...)` raise `ValueError: '333333' is not a valid value for color` at the first color-taking call, not at import — grep every `color=` in the plt section before running the builder.
    - **`ax.legend([handle, ...])` with a bare list of artists raises `TypeError: A single argument passed to legend() must be a list of labels`** — matplotlib reads one positional arg as labels. Call `ax.legend(handles, [h.get_label() for h in handles], ...)` (or two parallel lists) when the handles are Patch/Line2D objects; `bar(..., label=)` legends need no fix.
- **Native tools on Windows: forward-slash native paths, never MSYS `/e/` in a native argument.** Native python.exe / gh / rg received from bash as `/e/workbuddy/...` fail (`E:\e\workbuddy\...` — MSYS conversion is off here); pass `E:/workbuddy/...`. The skill scripts live under `E:/workbuddy/国外模型/hermes/skills/productivity/docx/scripts/`; run with whatever python has python-docx (the Hermes tools python, installed on demand via `"$PYBIN" -m pip install python-docx`) — check with `import docx` before assuming.
- **The execute_code kernel cannot build or verify docx on this host (its lxml is broken: `import docx` → "cannot import name 'etree'").** Do create + verify from `terminal` with a venv python that has working python-docx + lxml. Known-good runners: `E:/workbuddy/国外模型/hermes/hermes-agent/venv/Scripts/python.exe` (the plain tools python-3.14.9 ships WITHOUT python-docx; `D:/jince_sass/.venv` and `D:/workbuddy/binaries/python/versions/3.13.12/python.exe` are the other known-good). One-liner: `<venv-python> E:/workbuddy/国外模型/hermes/skills/productivity/docx/scripts/docx_create.py spec.json out.docx`, then verify with `.../docx_read.py out.docx --structure` (expect the heading outline + table shapes; TOC/fields show as placeholders until Word opens the file).
- **Don't unzip-and-sed the XML.** Edit through the scripts (or
  python-docx); raw text substitution in `document.xml` corrupts files
  easily. Use `patch`/`write_file` only for the JSON inputs, never on the
  `.docx` itself.

## Verification

- After create/edit/template, run `docx_read.py out.docx --text` and
  check the expected strings appear (and old strings are gone).
- After accept/reject, `docx_revisions.py list` should return `[]` (or
  only the ids you intentionally left); after comment surgery,
  `docx_comments.py list` should reflect the change and `--text` output
  must be unchanged.
- `docx_validate.py out.docx` exits 0 with `"ok": true` on a healthy
  package — run it after any revision/comment/field manipulation.
- For templates run with `--strict`, or check `unfilled_tokens == []`.
- Structure checks: `--structure` should show the expected heading
  outline and table shapes; `--styles` confirms custom styles applied.
