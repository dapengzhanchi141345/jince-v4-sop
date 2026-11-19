# 终端切线自动执行: 唤醒terminal64 -> 菜单"文件->登录到交易账户" -> 服务器框输入trademax -> 选TradeMaxGlobal-Demo -> 登录
# Windows ctypes SendInput 盲操作 (无cua-driver依赖), 每步验证(读终端窗口标题/前台句柄)
import ctypes, time, sys
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# 找 terminal64 主窗口
hwnd = user32.FindWindowW(None, "TMGM MT5 Terminal")
if not hwnd:
    # 尝试枚举
    found = []
    def cb(h, _):
        n = user32.GetWindowTextLengthW(h)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(h, buf, n + 1)
            if "Terminal" in buf.value or "MT5" in buf.value:
                found.append((h, buf.value))
        return True
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(cb), 0)
    print("枚举到窗口:", found)
    if found:
        hwnd = found[0][0]
if not hwnd:
    print("FIND_WINDOW_FAIL"); sys.exit(1)
print("主窗口 hwnd:", hex(hwnd))

def key_down(code):
    INPUT_KEYBOARD = 5
    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.POINTER(ctypes.c_long))]
    class INPUT(ctypes.Structure):
        class _U(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT)]
        _fields_ = [("type", wintypes.DWORD), ("u", _U)]
    def send(vk, flags):
        i = INPUT()
        i.type = INPUT_KEYBOARD
        i.u.ki.wVk = vk
        i.u.ki.dwFlags = flags
        i.u.ki.dwExtraInfo = ctypes.cast(ctypes.c_long(0), ctypes.POINTER(ctypes.c_long))
        user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(INPUT))
    return send

# VK 码
VK = {"TAB": 0x09, "ENTER": 0x0D, "ESCAPE": 0x1B, "DOWN": 0x28, "UP": 0x26,
      "ALT": 0x12, "F": 0x46, "L": 0x4C, "T": 0x54, "G": 0x47, "O": 0x4F, "R": 0x52,
      "A": 0x41, "D": 0x44, "M": 0x4D, "E": 0x45, "X": 0x58, "N": 0x4E,
      "BACK": 0x08, "DELETE": 0x2E}
KEYEVENTF_KEYUP = 2

def press(name, delay=0.06):
    send = key_down(0)
    send(VK[name], 0)
    time.sleep(delay)
    send(VK[name], KEYEVENTF_KEYUP)
    time.sleep(delay)

def type_str(s, per=0.04):
    for ch in s:
        if ch.isalpha():
            press(ch.upper(), per)
        elif ch.isdigit():
            # 数字用小键盘关闭, 主键盘
            press({"0":"ZERO".ljust(1)} if False else ch, per)
        time.sleep(0.01)

# 数字VK
def press_digit(d):
    VKD = {"0":0x30,"1":0x31,"2":0x32,"3":0x33,"4":0x34,"5":0x35,"6":0x36,"7":0x37,"8":0x38,"9":0x39}
    send = key_down(0)
    send(VKD[d], 0); time.sleep(0.05); send(VKD[d], KEYEVENTF_KEYUP); time.sleep(0.05)

# 1) 唤起到前台
user32.ShowWindow(hwnd, 9)  # SW_RESTORE
user32.SetForegroundWindow(hwnd)
time.sleep(1.0)
fg = user32.GetForegroundWindow()
print("前台窗口:", hex(fg), "目标:", hex(hwnd), "匹配:", fg == hwnd)
if fg != hwnd:
    # 经典trick: 模拟Alt键解锁
    press("ALT")
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.8)
    fg = user32.GetForegroundWindow()
    print("二次尝试前台:", hex(fg) == hex(hwnd))

# 2) Alt+F 打开"文件"菜单
press("ALT", 0.15)
press("F", 0.2)
time.sleep(0.5)
# 文件菜单 -> "登录到交易账户" (File->Login to Trade Account): 按 菜单项 (中文MT5: 文件菜单第2项附近)
# 盲操作: 用 F10/Down 导航不可靠 -> 用已知快捷键: MT5 "文件"菜单无统一快捷键, 改走"工具->选项"更稳? 
# 最稳路线: 直接按 Ctrl+L (登录对话框) 试一次
press("ESCAPE")  # 关菜单
time.sleep(0.3)
press("ALT", 0.1)
press("L", 0.2)  # Ctrl不可靠, 先试 菜单路径: 文件->登录 (盲)
time.sleep(1.0)
print("步骤1完成: 菜单/快捷键已发, 接下来用标题判断是否出现登录对话框")
# 判断对话框: EnumWindows 找子窗口/新顶层窗口
found = []
def cb2(h, _):
    if user32.IsWindow(h) and user32.IsWindowVisible(h):
        n = user32.GetWindowTextLengthW(h)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(h, buf, n + 1)
            t = buf.value
            if any(k in t for k in ["登录", "Login", "log in", "账户", "Account"]):
                found.append((h, t))
    return True
user32.EnumWindows(WNDENUMPROC(cb2), 0)
print("对话框候选:", found)
if found:
    user32.SetForegroundWindow(found[0][0])
    time.sleep(0.8)
    print("已聚焦登录对话框, 下一步: 服务器框输入trademax (本脚本到此为止, 后续由外层按验证结果决定)")
    print("DIALOG_FOUND")
else:
    print("DIALOG_NOT_FOUND (快捷键未命中, 需像素级菜单点击)")
