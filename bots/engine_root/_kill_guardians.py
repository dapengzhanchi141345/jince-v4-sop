# -*- coding: utf-8 -*-
import os, sys, struct, subprocess, ctypes
from ctypes import wintypes, c_char, c_ulong, byref, c_void_p

_k32 = ctypes.windll.kernel32
_ntdll = ctypes.windll.ntdll
_k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_k32.OpenProcess.restype = wintypes.HANDLE
_k32.CloseHandle.argtypes = [wintypes.HANDLE]
_k32.CloseHandle.restype = wintypes.BOOL
_ntdll.NtQueryInformationProcess.argtypes = [wintypes.HANDLE, c_ulong, c_void_p, c_ulong, ctypes.POINTER(c_ulong)]
_ntdll.NtQueryInformationProcess.restype = c_ulong
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

def get_cmdline(pid):
    h = _k32.OpenProcess(0x0400, False, pid)
    if not h: return ""
    try:
        buf = (c_char * 16384)()
        ret = c_ulong()
        if _ntdll.NtQueryInformationProcess(h, 60, buf, 16384, byref(ret)) != 0: return ""
        length = struct.unpack_from("<H", buf, 0)[0]
        if length <= 0: return ""
        bp = struct.unpack_from("<Q", buf, 8)[0]
        off = bp - ctypes.addressof(buf)
        if not (0 <= off < 16384): off = 12
        return bytes(buf[off:off+length]).decode("utf-16-le", "replace")
    finally:
        _k32.CloseHandle(h)

r = subprocess.run(["tasklist","/FO","CSV","/NH"], capture_output=True, creationflags=NO_WINDOW, timeout=30)
me = os.getpid()
killed = []
for ln in (r.stdout or b"").decode("utf-8","replace").splitlines():
    parts = [p.strip('"') for p in ln.split(",")]
    if len(parts) >= 2 and parts[1].isdigit():
        pid = int(parts[1])
        if pid == me: continue
        cl = get_cmdline(pid)
        if "boot_guardian" in cl:
            try:
                os.kill(pid, 9)
                killed.append(pid)
            except Exception as e:
                killed.append(("err", pid, str(e)))
print("killed:", killed)
