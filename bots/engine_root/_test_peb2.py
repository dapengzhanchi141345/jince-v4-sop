# -*- coding: utf-8 -*-
import ctypes, struct, subprocess
from ctypes import wintypes, c_char, c_ulong, byref, c_void_p

kernel32 = ctypes.windll.kernel32
ntdll = ctypes.windll.ntdll
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
ntdll.NtQueryInformationProcess.argtypes = [wintypes.HANDLE, c_ulong, c_void_p, c_ulong, ctypes.POINTER(c_ulong)]
ntdll.NtQueryInformationProcess.restype = c_ulong

PROCESS_QUERY_INFORMATION = 0x0400

def get_cmdline(pid):
    h = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        size = 16384
        buf = (c_char * size)()
        retlen = c_ulong()
        status = ntdll.NtQueryInformationProcess(h, 60, buf, size, byref(retlen))
        if status != 0:
            return ""
        length = struct.unpack_from("<H", buf, 0)[0]   # UNICODE_STRING.Length (bytes)
        if length <= 0:
            return ""
        # 读取 UNICODE_STRING.Buffer 指针（x64 下位于偏移 8 的 8 字节），计算字符串真实偏移
        buf_ptr = struct.unpack_from("<Q", buf, 8)[0]
        buf_addr = ctypes.addressof(buf)
        offset = buf_ptr - buf_addr
        if not (0 <= offset < size):
            offset = 12  # 退化兜底
        raw = bytes(buf[offset:offset + length])
        return raw.decode("utf-16-le", "replace")
    except Exception:
        return ""
    finally:
        kernel32.CloseHandle(h)

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
r = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, creationflags=NO_WINDOW, timeout=30)
pids = []
for ln in (r.stdout or b"").decode("utf-8", "replace").splitlines():
    parts = [p.strip('"') for p in ln.split(",")]
    if len(parts) >= 2 and parts[1].isdigit():
        pids.append(int(parts[1]))

nonempty = 0
found = 0
for pid in pids:
    cl = get_cmdline(pid)
    if cl:
        nonempty += 1
        if any(k in cl for k in ("runner.py","auto_run_cycle","hermes.exe serve","jince_watchdog","event_guard","Hermes_Gateway")):
            found += 1
            print(">>", cl[:170])
print("total pids:", len(pids), " non-empty cmdlines:", nonempty, " relevant:", found)
