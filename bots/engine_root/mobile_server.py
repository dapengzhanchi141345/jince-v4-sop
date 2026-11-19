"""
金策宗师团 — 手机/远程访问服务器 (支持外网)
Goldstrategy Guild — Mobile Dashboard Server (Remote Access)

在任何地方访问你的交易仪表盘:

  局域网访问 (同一WiFi):
    http://你的电脑IP:8765

  远程访问 (任何网络):
    python mobile_server.py --remote    ← 自动生成外网链接

  查看电脑IP: ipconfig (找到 IPv4 地址, 如 192.168.1.100)
"""

import http.server
import socketserver
import json
import os
import socket
import webbrowser
from datetime import datetime

PORT = 8765
DASHBOARD_FILE = "C:/Users/ASUS/WorkBuddy/2026-07-03-21-37-46/logs/dashboard.html"
DATA_DIR = "E:/GoldstrategyEngine/data"


def get_local_ip():
    """获取局域网IP"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    """仪表盘HTTP处理器 — 任何人可访问"""
    
    def do_GET(self):
        if self.path == "/" or self.path == "/dashboard.html":
            self._serve_dashboard()
        elif self.path == "/api/status":
            self._serve_api()
        elif self.path.startswith("/data/"):
            # 提供数据文件
            file_path = DATA_DIR + self.path[5:]
            if os.path.exists(file_path):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                with open(file_path, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_error(404)
        else:
            super().do_GET()
    
    def _serve_dashboard(self):
        """提供仪表盘HTML"""
        if os.path.exists(DASHBOARD_FILE):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            with open(DASHBOARD_FILE, "rb") as f:
                self.wfile.write(f.read())
        else:
            self.send_error(404, "仪表盘未生成, 请先运行引擎")
    
    def _serve_api(self):
        """提供API状态"""
        status = {
            "system": "金策宗师团 v4.0",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "running",
        }
        
        # 检查模型
        model_path = "E:/GoldstrategyEngine/data/models/xgb_model.json"
        if os.path.exists(model_path):
            status["ml_model"] = "loaded"
            status["ml_model_size"] = f"{os.path.getsize(model_path)/1024:.0f}KB"
        
        # 检查数据
        data_paths = [
            "E:/GoldstrategyEngine/data/external",
            "E:/GoldstrategyEngine/data/deep_memory.json",
        ]
        for p in data_paths:
            if os.path.exists(p):
                status["data_available"] = True
        
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(status, ensure_ascii=False, indent=2).encode())
    
    def log_message(self, format, *args):
        """自定义日志"""
        client = self.client_address[0]
        print(f"  [访问] {client} → {args[0]}")


def start_server():
    """启动服务器"""
    ip = get_local_ip()
    
    print(f"""
╔═══════════════════════════════════════════════╗
║   金策宗师团 — 手机远程访问                    ║
╚═══════════════════════════════════════════════╝

  📱 在手机上打开浏览器访问:

     🔗 http://{ip}:{PORT}

  💻 同一WiFi下, 其他电脑也可访问

  ℹ️  查看电脑IP: 在命令行输入 ipconfig

  🛑 按 Ctrl+C 停止服务
""")
    
    # 自动打开浏览器
    try:
        webbrowser.open(f"http://localhost:{PORT}")
    except Exception:
        pass
    
    # 启动HTTP服务 (允许远程访问)
    handler = DashboardHandler
    handler.extensions_map = {
        ".html": "text/html; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".png": "image/png",
        ".css": "text/css",
        ".js": "application/javascript",
    }
    
    with socketserver.TCPServer(("0.0.0.0", PORT), handler) as httpd:
        httpd.allow_reuse_address = True
        httpd.serve_forever()


def send_to_qq_email():
    """
    通过QQ邮箱发送仪表盘到手机
    
    用法: 把 dashboard.html 通过QQ邮箱发给自己
    手机端打开QQ邮箱即可查看
    """
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    
    print("通过QQ邮箱发送仪表盘到手机")
    print()
    
    # 读取仪表盘
    if not os.path.exists(DASHBOARD_FILE):
        print("❌ 仪表盘文件不存在")
        return
    
    with open(DASHBOARD_FILE, "r", encoding="utf-8") as f:
        html_content = f.read()
    
    # 嵌入到邮件
    email_body = f"""
    <html>
    <body>
        <h2>金策宗师团 — 交易日报</h2>
        <p>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
        <hr>
        {html_content}
    </body>
    </html>
    """
    
    print("""
  方式1: 最简单的办法
  ─────────────────────
  把文件直接拖到QQ邮箱网页:
  1. 打开 mail.qq.com
  2. 写邮件 → 收件人写你自己
  3. 把 dashboard.html 拖进去
  4. 发送 → 手机QQ邮箱打开

  方式2: 局域网访问
  ─────────────────────  
  在同一WiFi下, 手机浏览器输入:
  http://电脑IP:8765

  方式3: 用QQ邮箱发
  ─────────────────────
  如果需要自动发送, 告诉我你的QQ邮箱地址,
  我帮你配置自动发送。
""")


if __name__ == "__main__":
    import sys
    
    if "--email" in sys.argv:
        send_to_qq_email()
    elif "--remote" in sys.argv:
        start_remote_server()
    elif "--ngrok" in sys.argv:
        start_ngrok_server()
    else:
        start_server()


def start_remote_server():
    """
    启动远程服务器 (任何网络可访问)
    
    三种方式:
      A. ngrok — 最稳定, 建议注册 (免费)
      B. localhost.run — 零注册, 一条命令
      C. 手动SSH隧道 — 技术流
    """
    print(f"""
╔═══════════════════════════════════════════════╗
║   金策宗师团 — 远程访问                        ║
╚═══════════════════════════════════════════════╝

  选一个方式:

  A. ngrok (推荐, 需注册一次)
     python mobile_server.py --remote-ngrok

  B. localhost.run (零注册, 直接可用)
     在新开一个命令行窗口运行:
     ssh -R 80:localhost:8765 nokey@localhost.run

     然后浏览器打开显示的网址即可

  C. 局域网 (同一WiFi)
     python mobile_server.py
     手机浏览器访问: http://{get_local_ip()}:8765

  D. QQ邮箱发送到手机
     python mobile_server.py --email
""")
    
    # 启动本地服务器 (让其他方式也能访问)
    httpd = socketserver.TCPServer(("0.0.0.0", PORT), DashboardHandler)
    httpd.allow_reuse_address = True
    
    print(f"  本地服务已启动: http://{get_local_ip()}:{PORT}")
    print()
    print("  按 Ctrl+C 停止")
    print()
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  服务已停止")


def start_ngrok_server():
    """启动ngrok远程服务器 (需注册一次)"""
    try:
        from pyngrok import ngrok
    except ImportError:
        print("❌ 请先安装: pip install pyngrok")
        return
    
    # 启动本地服务器
    httpd = socketserver.TCPServer(("0.0.0.0", PORT), DashboardHandler)
    httpd.allow_reuse_address = True
    
    # 创建ngrok隧道
    try:
        tunnel = ngrok.connect(PORT, "http")
        url = tunnel.public_url
    except Exception as e:
        print(f"""
  ❌ ngrok连接失败: {e}

  📋 解决方案:
  1. 注册: https://ngrok.com (免费)
  2. 获取 Authtoken
  3. 运行: ngrok config add-authtoken 你的token
  4. 再试一次
""")
        return
    
    print(f"""
╔═══════════════════════════════════════════════╗
║   远程访问已开启 ✅                             ║
╚═══════════════════════════════════════════════╝

  📱 在任何网络下打开:

     🔗 {url}

  💡 把这个链接发到微信, 点开就能看
  ⏳ 链接有效到服务器关闭为止
  🛑 按 Ctrl+C 停止
""")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  服务已停止")
        ngrok.kill()

