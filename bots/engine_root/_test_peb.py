# -*- coding: utf-8 -*-
import ctypes, glob, os
from ctypes import wintypes, Structure, POINTER, byref, c_void_p, c_ulong, c_ulonglong, c_ushort

kernel32 = ctypes.windll.kernel32
ntdll = ctypes.windll.ntdll

kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.ReadProcessMemory.argtypes = [wintypes.HANDLE, c_void_p, c_void_p, c_ulonglong, POINTER(c_ulonglong)]
kernel32.ReadProcessMemory.restype = wintypes.BOOL
ntdll.NtQueryInformationProcess.argtypes = [wintypes.HANDLE, c_ulong, c_void_p, c_ulong, POINTER(c_ulong)]
ntdll.NtQueryInformationProcess.restype = c_ulong

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
PROCESS_ALL_ACCESS = 0x1F0FFF

class PROCESS_BASIC_INFORMATION(Structure):
    _fields_ = [("Reserved1", c_void_p), ("PebBaseAddress", c_void_p),
                ("Reserved2", c_void_p), ("UniqueProcessId", c_void_p), ("Reserved3", c_void_p)]

class UNICODE_STRING(Structure):
    _fields_ = [("Length", c_ushort), ("MaximumLength", c_ushort), ("Buffer", c_void_p)]

def get_cmdline(pid):
    h = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    if not h:
        return ""
    try:
        pbi = PROCESS_BASIC_INFORMATION()
        retlen = c_ulong()
        st = ntdll.NtQueryInformationProcess(h, 0, byref(pbi), sizeof(pbi), byref(retlen))
        if st != 0 or not pbi.PebBaseAddress:
            return ""
        pp = c_void_p()
        if not kernel32.ReadProcessMemory(h, c_void_p(pbi.PebBaseAddress + 0x20), byref(pp), 8, None):
            return ""
        if not pp:
            return ""
        us = UNICODE_STRING()
        if not kernel32.ReadProcessMemory(h, c_void_p(pp + 0x70), byref(us), sizeof(us), None):
            return ""
        if not us.Buffer or us.Length == 0:
            return ""
        buf = ctypes.create_unicode_buffer(us.Length // 2 + 1)
        if not kernel32.ReadProcessMemory(h, us.Buffer, buf, us.Length, None):
            return ""
        return buf.value or ""
    except Exception as e:
        return ""
    finally:
        kernel32.CloseHandle(h)

# 枚举所有 pid（用 tasklist 拿 pid 列表，再用 PEB 读 cmdline）
import subprocess
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
r = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, creationflags=NO_WINDOW, timeout=30)
pids = []
for ln in (r.stdout or b"").decode("utf-8", "replace").splitlines():
    parts = [p.strip('"') for p in ln.split(",")]
    if len(parts) >= 2 and parts[1].isdigit():
        pids.append(int(parts[1]))

found = 0
for pid in pids:
    cl = get_cmdline(pid)
    if cl and ("runner.py" in cl or "auto_run_cycle" in cl or "hermes.exe serve" in cl or "jince_watchdog" in cl or "event_guard" in cl):
        found += 1
        print(">>", cl[:170])
print("total pids:", len(pids), " relevant found:", found)
