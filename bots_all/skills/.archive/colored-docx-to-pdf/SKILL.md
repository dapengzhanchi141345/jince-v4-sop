---
name: colored-docx-to-pdf
description: "White-bg colored Word→PDF via python-docx + Word COM. 也覆盖『精美 PDF』呈报/复盘报告：单文件 HTML+内嵌矢量 SVG → Edge 无头 print-to-pdf（零 pip 依赖，本机 msedge.exe 已装），白底金/玉/朱配色，模板见 templates/precise_report.html + templates/html2pdf_edge.py。"
version: 1.1.0
---

# 彩色 Word → PDF 文档交付（Windows）

Class: 生成带配色、表格、标题、协作署名的 Word 文档，并自动转 PDF，全部 Windows + Python 完成，无需用户手开 Word。本技能是本用户「按最高标准出结果、版式色彩精美、必须白底、署名让给协作人」诉求的可靠路径。

核心链路：`python-docx` 生成 `.docx` → Word COM（`comtypes`）自动转 `.pdf`。装依赖：`python -m pip install python-docx comtypes pypdf`。

## 何时用

- 用户要「色彩精美」「版式美化」「PDF 呈报版」的 Word/建议书/报告/量表/表单。
- 需要白底学术配色（深色底/玄墨底被明确否掉：用户说「这样的底色不行，要 Word 转 PDF 才行」）。
- 成果要「让给协作人」/联合署名（提出人放次要位）。
- 纯 HTML→PDF（Edge 无头）深色版用户不接受；要白底 + 可编辑 .docx 双件时走本技能。

## 固定工作流（按顺序，每步有闸门）

0. **判底**：受众是屏幕交互（课件/看板）→ 可用深色「玄金红」板；受众是纸质/会议/呈报领导 → **必须白底**（本用户否决过深色呈报 PDF）。
1. **定白底三色体系并验对比度**（写码前做，别凭感觉）：用相对亮度公式算每对「文字/背景」`(L1+0.05)/(L2+0.05)`，正文需 ≥4.5:1、大字/表头白字需 ≥3:1，不过就调。复用值见文末「配色铁律」（已验全过 4.5:1）。
2. **加协作署名表（文首）**：一张表，行=提出人/协作人/协作单位/成果归属/日期；「成果归属」写明「本成果归协作团队共同所有，署名顺序以联合署名为准」；提出人（李彦明）放次要位。人名以用户当次点名为准，勿沿用旧名单。
3. **python-docx 生成 .docx**：
   - 字体：正文宋体 10.5pt、标题黑体加粗、引文/表格 9–9.5pt；`run._element.get_or_add_rPr()` 设 `w:rFonts w:eastAsia`（中文不糊）。
   - 表格：`style='Table Grid'`；表头格 `OxmlElement('w:shd')` 设 `w:fill` 金底 `D8B45A` + 白字加粗黑体；首列常加粗上色（金/玉青）。
   - 竖条标题：`w:pBdr/w:left`（金 `8a6210`，sz 18）；引文/警示块用单格表 + `shd`（玉青浅 `DCEFE4` / 朱砂浅 `F3DEDA`）+ 对应边框色。
   - 页面：`sections[0].top/bottom_margin=Cm(2.0)`、`left/right=Cm(2.2)`。
   - **陷阱**：`OxmlElement.set(qn('w:color'), ...)` 只收 **hex 字符串**，传 `RGBColor` 即 `TypeError: Argument must be bytes or unicode, got 'RGBColor'`。所有 `w:color`/`w:fill` 一律传字符串（`'8a6210'`、`'D8B45A'`）。
4. **Word COM 自动转 PDF**（本机 Office16）：
   ```python
   import comtypes.client, os
   w = comtypes.client.CreateObject("Word.Application"); w.Visible=False; w.DisplayAlerts=0
   d = w.Documents.Open(os.path.abspath(docx_path))
   d.SaveAs2(os.path.abspath(pdf_path), FileFormat=17)  # 17=wdFormatPDF
   d.Close(False); w.Quit()
   ```
5. **双件交付 + 校验**：同目录出 `.docx`（可改）+ `.pdf`（呈报）；`pypdf.PdfReader` 抽第 1 页确认署名表在位、表头金块/朱砂警示块渲染正常；报两份路径 + 页数 + 大小。落 `E:\workbuddy\内容中心\` 体系。

## md→白底 Word→PDF 通用转换器

任意 `.md` 一键转白底彩色 Word + PDF：用 `templates/md2word_pdf.py`（自动插协作署名表；解析标题/表/引用/列表/代码；金底表头 + 玉青引文 + 朱砂警示）。命令 `python E:/workbuddy/工具/md2word_pdf.py a.md b.md ...`。主建议书（带封面摘要 + 署名表 + 全章节）专用脚本见 `templates/build_docx_white.py`（两者已落 `E:\workbuddy\工具\`，可直接复用/修改）。

## 精美 PDF 默认路径（用户『以后给我转换成精美的 pdf』）

用户要『精美 PDF 呈报/复盘/交易报告』时，**首选单文件 HTML + 内嵌矢量 SVG → Edge 无头转 PDF**，比 docx+COM 更精美（可完整用 KPI 卡片/flex/色块/渐变），且本机零 pip 依赖：

1. 生成 HTML：复制 `templates/precise_report.html`，替换 `{{占位符}}`；**图表一律内联 SVG**（`<svg viewBox="0 0 800 3xx" font-family="Microsoft YaHei">`），别用位图，PDF 里更清晰。
2. 转 PDF：`python templates/html2pdf_edge.py in.html out.pdf`（自动找 msedge.exe，临时 user-data-dir，忽略 stderr 噪音；成功=stdout `bytes written` + 文件存在非零）。
3. 配色铁律同本文「配色铁律」（白底，已验 4.5:1）；中文务必 `font-family:"Microsoft YaHei"`；`@page{size:A4;margin:16mm 14mm}`；表格/色块 `page-break-inside:avoid` 防跨页断裂。
4. 交付 `.pdf`（可再附 `.html` 源）；用 pypdf 抽第 1 页文字确认中文渲染正常再报。
   - Edge 常见坑：`--user-data-dir` 必须给干净临时目录（指向真实 profile 会锁冲突）；stderr 的 sync/importer/LOADERROR 全是噪音，看 stdout `N bytes written` 才算成功。

> 何时走 docx+COM 而非本路径：要**可编辑 .docx 双件**（用户可改稿）时走 python-docx+Word COM；只要**呈报/复盘 PDF**时走本 HTML+Edge 路径。

## 关键 Pitfalls

- **WeasyPrint 在 Windows 跑不起来**：FFI 需 GTK3/Pango（`libgobject-2.0`），本机没有；`winget search pango` 只有 PangoTerm，`choco/conda/vcpkg/nuget` 未装，网络常连不上 github 拉 DLL。别在这条路上耗——彩色 PDF 一律走「python-docx + Word COM」或「HTML + Edge 无头 `--print-to-pdf`」。Edge 路径（完整 CSS/flex/grid/渐变 1:1，比 WeasyPrint 强；适合深色屏幕版，白底呈报版优先 docx+COM）：`"C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" --headless=new --disable-gpu --no-sandbox --user-data-dir=<tmp> --print-to-pdf-no-header --print-to-pdf=<out.pdf> --virtual-time-budget=12000 file:///<html>`。`--user-data-dir` 必须给干净临时目录（指向用户真实 profile 会锁冲突）；stderr 的 sync/importer ERROR 全是噪音，看 stdout `N bytes written to file` 才算成功。
- **要内嵌矢量图表（净值曲线/分箱图）走 Edge 路径**：docx+Word COM 只能嵌位图（先画图再插入）；HTML 直接内联 SVG 零依赖（本机各 venv 都没装 matplotlib，别中途 pip install）。生成后用 pypdf 抽每页前 60 字确认章节断页没乱（pypdf 装在 `ate` venv：`C:/Users/ASUS/.workbuddy/binaries/python/envs/ate/Scripts/python.exe`，缺则 `-m pip install pypdf`）。版式技巧：KPI 卡片用 flex + `border-top` 色条；表格/色块加 `page-break-inside: avoid` 防跨页断裂。
- **python-docx `OxmlElement.set` 只收字符串**：`w:color`/`w:fill` 传 `RGBColor` 即崩，全程 hex 字符串。
- **深色底 ≠ 呈报版**：本用户「玄金红」深色板只用于屏幕 HTML；一涉「打印/投影/呈报教育局」就切白底。判据：受众屏幕交互→深色；受众纸质/会议→白底。
- **署名归属**：所有成品「成果归属」行必须写归协作团队共同所有、署名顺序以联合署名为准；提出人放次要位（用户多次纠正「我是协作人才行，把成果让给他们」）。

## 配色铁律（白底，已验全过 4.5:1）

正文 `#1a1a1a`；深墨金（标题/表头字）`#8a6210`；表头金底 `#D8B45A`+白字；玉青（正向/引文字）`#1f6b4a`+浅底 `#DCEFE4`；朱砂（警示/负向）`#9e2a20`+浅底 `#F3DEDA`；浅金要点底 `#F5EBD0`；次要灰 `#595959`。字体：正文宋体、标题黑体、引文表格 9–9.5pt。

## 用 docx 技能 docx_create.py 出 spec JSON 的坑（本用户铁律：分析报告一律精美 Word 走 docx_create.py 生成+验证存 内容中心\交付\）
当走 `docx` 技能的 `scripts/docx_create.py spec.json out.docx`（而非本技能 templates 的 OxmlElement 路径）时：
- **`styles` 必须是 list**（每项 `{"name":...,"base":"Normal","font":...}`），传按样式名建键的 dict → `TypeError: string indices must be integers, not 'str'`。
- **`color` 一律 6 位 hex 不带 `#`**：脚本内部 `int(c[:2],16)` 解析，带 `#` → `ValueError: invalid literal for int() with base 16: '#1'`。
- **python-docx 常没装在 ATE venv**：先 `C:/Users/ASUS/.workbuddy/binaries/python/envs/ate/Scripts/python.exe -m pip install python-docx` 再跑 create/read。
- **spec JSON 别手写**：正文含中英文引号混用会 `JSONDecodeError`（write_file 的 JSON 校验也拦）。用 Python `dict` 构造 + `json.dump(..., ensure_ascii=False)` 落盘最稳。
- **生成后验**：`docx_read.py out --structure`（验章节 outline + 表格形状都在）+ `docx_validate.py out`（`ok:true` 才报）；落 `E:\workbuddy\内容中心\交付\`，报路径+大小+章节数。
- 对客/呈报物料先按 B 档 0 方向词/0 收益承诺/0 实盘数据 自检再落（草稿态），复检过才翻正式版。

## 验证

- 生成后 `PdfReader` 抽第 1 页文字：署名表（协作署名·联合成果 / 提出人 / 协作人 / 成果归属）应在位；金/朱色块渲染正常。
- 报双件 `<名>.docx` + `<名>.pdf`（均落 `E:\workbuddy\内容中心\`）。
