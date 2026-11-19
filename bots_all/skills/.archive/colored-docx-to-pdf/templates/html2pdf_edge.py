"""精美白底报告 HTML → PDF（单文件，Edge 无头，内嵌矢量 SVG 图表）。
用法: python html2pdf_edge.py in.html out.pdf
本用户「精美 PDF」默认路径：白底 + 金/玉/朱配色 + KPI卡片/色块/警示框 + 内嵌 SVG 图，
Edge --headless --print-to-pdf 转制，零 pip 依赖（Edge 本机已有）。
配套精美 HTML 骨架见同目录 precise_report.html（占位符 {{ }} 直接替换）。

配色铁律（白底，已验对比度）：正文 #1a1a1a；深墨金标题/表头字 #8a6210；表头金底 #D8B45A+白字；
玉青(正向) #1f6b4a+浅底 #DCEFE4；朱砂(警示/负向) #9e2a20+浅底 #F3DEDA；浅金要点底 #F5EBD0；次要灰 #595959。
中文字体务必 font-family:"Microsoft YaHei"（Edge 打印能正确带 CJK）。
"""
import sys, os, tempfile, subprocess, shutil

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

def find_edge():
    for p in EDGE_CANDIDATES:
        if os.path.exists(p):
            return p
    return shutil.which("msedge")

def html_to_pdf(html_path, pdf_path):
    edge = find_edge()
    if not edge:
        raise RuntimeError("找不到 msedge.exe，请确认已安装 Microsoft Edge")
    html_path = os.path.abspath(html_path)
    pdf_path = os.path.abspath(pdf_path)
    tmp = tempfile.mkdtemp(prefix="edge_pdf_")
    cmd = [
        edge, "--headless=new", "--disable-gpu", "--no-sandbox",
        f"--user-data-dir={tmp}",
        "--print-to-pdf-no-header",
        f"--print-to-pdf={pdf_path}",
        "--virtual-time-budget=12000",
        f"file:///{html_path.replace(os.sep, '/')}",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    shutil.rmtree(tmp, ignore_errors=True)
    # 成功标志: stdout 含 "bytes written"; 常见 stderr 的 sync/importer/LOADERROR 都是噪音, 忽略
    ok = os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0
    hint = "bytes written" in (r.stdout or r.stderr or "")
    return {"ok": ok, "hint": hint, "pdf": pdf_path, "bytes": os.path.getsize(pdf_path) if ok else 0,
            "stderr_tail": (r.stderr or "")[-300:]}

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__); sys.exit(1)
    res = html_to_pdf(sys.argv[1], sys.argv[2])
    print(res)
    sys.exit(0 if res["ok"] else 2)
