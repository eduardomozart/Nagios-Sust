import os
import ctypes
from ctypes import wintypes

class OPENFILENAMEW(ctypes.Structure):
    _fields_ = [
        ("lStructSize", wintypes.DWORD),
        ("hwndOwner", wintypes.HWND),
        ("hInstance", wintypes.HINSTANCE),
        ("lpstrFilter", wintypes.LPCWSTR),
        ("lpstrCustomFilter", wintypes.LPWSTR),
        ("nMaxCustFilter", wintypes.DWORD),
        ("nFilterIndex", wintypes.DWORD),
        ("lpstrFile", wintypes.LPWSTR),
        ("nMaxFile", wintypes.DWORD),
        ("lpstrFileTitle", wintypes.LPWSTR),
        ("nMaxFileTitle", wintypes.DWORD),
        ("lpstrInitialDir", wintypes.LPCWSTR),
        ("lpstrTitle", wintypes.LPCWSTR),
        ("Flags", wintypes.DWORD),
        ("nFileOffset", wintypes.WORD),
        ("nFileExtension", wintypes.WORD),
        ("lpstrDefExt", wintypes.LPCWSTR),
        ("lCustData", wintypes.LPARAM),
        ("lpfnHook", wintypes.LPVOID),
        ("lpTemplateName", wintypes.LPCWSTR),
        ("pvReserved", wintypes.LPVOID),
        ("dwReserved", wintypes.DWORD),
        ("FlagsEx", wintypes.DWORD),
    ]

def open_file_dialog(title="Select File", file_filter="All files (*.*)\0*.*\0\0"):
    """
    Opens a native Windows file selection dialog.
    Returns the absolute path to the selected file, or None if cancelled.
    """
    MAX_PATH = 260
    
    ofn = OPENFILENAMEW()
    ofn.lStructSize = ctypes.sizeof(OPENFILENAMEW)
    ofn.hwndOwner = 0
    
    ofn.lpstrFilter = file_filter
    ofn.nFilterIndex = 1
    
    file_buffer = ctypes.create_unicode_buffer(MAX_PATH)
    ofn.lpstrFile = ctypes.cast(file_buffer, wintypes.LPWSTR)
    ofn.nMaxFile = MAX_PATH
    
    ofn.lpstrTitle = title
    
    # OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST
    ofn.Flags = 0x00001000 | 0x00000800
    
    # Show dialog
    if ctypes.windll.comdlg32.GetOpenFileNameW(ctypes.byref(ofn)):
        file_path = file_buffer.value
        if file_path and os.path.exists(file_path):
            return file_path
        
    return None
