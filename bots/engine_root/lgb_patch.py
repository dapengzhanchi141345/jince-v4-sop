"""
LightGBM DLL patch — ensures lib_lightgbm.dll is loadable.
Must be imported BEFORE any lightgbm import.
"""
import os
import ctypes

dll_dir = r'C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\Lib\site-packages\lightgbm\bin'

# Python 3.8+ supports os.add_dll_directory
if hasattr(os, 'add_dll_directory'):
    try:
        os.add_dll_directory(dll_dir)
    except Exception:
        pass

# Also add to PATH for good measure
os.environ['PATH'] = dll_dir + os.pathsep + os.environ.get('PATH', '')

# Pre-load the DLL to get any errors out early
try:
    ctypes.cdll.LoadLibrary(os.path.join(dll_dir, 'lib_lightgbm.dll'))
except Exception as e:
    print(f'[LGB] DLL preload warning (non-fatal): {e}')
