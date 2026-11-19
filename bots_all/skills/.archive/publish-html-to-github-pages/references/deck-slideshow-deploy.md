# PPT → online slideshow deploy (this host)
Recipe for the "把 PPT 部署到网上，打开网址就能看" class of task. The shared skill (SKILL.md)
holds the generic Pages procedure; this file holds the deck-specific pipeline and its pitfalls.

## Pipeline
1. **Render .pptx → PNG via PowerPoint COM.** LibreOffice is NOT usable here: `soffice` is not on
   PATH and `find / -name soffice*` hangs past timeout. Use the proven COM path:
   ```python
   import comtypes.client as cc
   ppt = cc.CreateObject("PowerPoint.Application"); ppt.Visible = 1
   pp = ppt.Presentations.Open(r"C:\path\to\deck.pptx", WithWindow=1)
   pp.SaveAs(render_dir, 18)   # 18 = SaveAsFilter.ppsx? -> PNG folder; 18 saves pngs
   pp.Close()
   ```
   Then kill PowerPoint so the next render starts clean:
   ```python
   import subprocess; subprocess.run(["taskkill","//F","//IM","POWERPNT.EXE"], capture_output=True)
   ```
   Rendered files are named `幻灯片1.PNG` … `幻灯片79.PNG`. Sort numerically with a regex on the
   filename digits, never with a listdir+`int()` on the whole name (the Chinese prefix crashes `int`).

2. **Build a single-file slideshow `index.html`.** Rules:
   - Compress each page to JPEG: `im.resize` to width 1600 if wider, `quality=85`. A 79-page deck
     lands around 9–11MB total, still well under GitHub's 50MB per-file limit.
   - Inline EVERY image as `data:image/jpeg;base64,` — no CDN, no external file. (User standing rule:
     self-contained single file works from `file://`.)
   - Navigation: keyboard ←/→/space/PageUp/PageDown/Home/End, `f` for fullscreen, swipe for mobile,
     a thumbnail index grid (click to jump), progress bar, and hash deep-link `#42` → page 42.
   - Nav titles: pull the first run with `font.size >= 28` on each slide; fall back to `第 N 页`.
   - Wrap `history.replaceState` in `if(history.replaceState)` — file:// has no history API.

3. **Deploy** with the standard Pages procedure in SKILL.md (isolated scratch repo holding only
   `index.html`). The pre-publish security grep applies to the slideshow HTML exactly as to any
   artifact: zero externals, zero secrets.

## Pitfalls
- `soffice` / global find for LibreOffice: do not attempt — wasted timeout. COM is the path.
- `int(f)` on `幻灯片12.PNG` → ValueError. Regex the digits: `int(re.search(r"\d+", name).group())`.
- base64-inlining PNGs raw would be ~3.9MB×79 ≈ 300MB. Always JPEG-compress to width 1600/q85 first.
- Don't publish the .pptx — GitHub Pages can't play it; the slideshow HTML is the artifact.
- If the deck is regenerated on a schedule, re-run the render→slideshow→publish chain; wire the
  template `sync_pages.py` so the shared URL tracks the latest deck instead of freezing.
