"""Process memory checkpoints for long renders (psutil optional)."""
from __future__ import annotations
import logging,os,sys

LOW_AVAILABLE_MB=1536.0
try:
    import psutil as _psutil
except ImportError:_psutil=None

def _windows_snapshot():
    import ctypes
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_=[("cb",wintypes.DWORD),("PageFaultCount",wintypes.DWORD),("PeakWorkingSetSize",ctypes.c_size_t),("WorkingSetSize",ctypes.c_size_t),("QuotaPeakPagedPoolUsage",ctypes.c_size_t),("QuotaPagedPoolUsage",ctypes.c_size_t),("QuotaPeakNonPagedPoolUsage",ctypes.c_size_t),("QuotaNonPagedPoolUsage",ctypes.c_size_t),("PagefileUsage",ctypes.c_size_t),("PeakPagefileUsage",ctypes.c_size_t),("PrivateUsage",ctypes.c_size_t)]
    class Status(ctypes.Structure):
        _fields_=[("dwLength",wintypes.DWORD),("dwMemoryLoad",wintypes.DWORD),("ullTotalPhys",ctypes.c_ulonglong),("ullAvailPhys",ctypes.c_ulonglong),("ullTotalPageFile",ctypes.c_ulonglong),("ullAvailPageFile",ctypes.c_ulonglong),("ullTotalVirtual",ctypes.c_ulonglong),("ullAvailVirtual",ctypes.c_ulonglong),("ullAvailExtendedVirtual",ctypes.c_ulonglong)]
    kernel32=ctypes.WinDLL("kernel32",use_last_error=True);psapi=ctypes.WinDLL("psapi",use_last_error=True)
    kernel32.GetCurrentProcess.restype=wintypes.HANDLE;kernel32.GetProcessHandleCount.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)];psapi.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.c_void_p,wintypes.DWORD]
    process=kernel32.GetCurrentProcess();counters=Counters();counters.cb=ctypes.sizeof(Counters);handles=wintypes.DWORD()
    psapi.GetProcessMemoryInfo(process,ctypes.byref(counters),counters.cb);kernel32.GetProcessHandleCount(process,ctypes.byref(handles))
    status=Status();status.dwLength=ctypes.sizeof(Status);kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
    return {"rss_mb":counters.WorkingSetSize/2**20,"private_mb":counters.PrivateUsage/2**20,"peak_rss_mb":counters.PeakWorkingSetSize/2**20,"peak_private_mb":counters.PeakPagefileUsage/2**20,"handles":int(handles.value),"threads":None,"available_mb":status.ullAvailPhys/2**20}

def snapshot()->dict:
    """Return rss/private/handles/threads/available memory; never raises."""
    try:
        if _psutil is not None:
            process=_psutil.Process();info=process.memory_info();result={"rss_mb":info.rss/2**20,"private_mb":getattr(info,"private",getattr(info,"vms",0))/2**20,"peak_rss_mb":getattr(info,"peak_wset",0)/2**20,"peak_private_mb":getattr(info,"peak_pagefile",0)/2**20,"handles":process.num_handles() if hasattr(process,"num_handles") else process.num_fds(),"threads":process.num_threads(),"available_mb":_psutil.virtual_memory().available/2**20}
            return result
        if sys.platform=="win32":return _windows_snapshot()
    except Exception:logging.debug("MEMORY snapshot failed",exc_info=True)
    return {"rss_mb":None,"private_mb":None,"peak_rss_mb":None,"peak_private_mb":None,"handles":None,"threads":None,"available_mb":None}

def _fmt(value):return "na" if value is None else (f"{value:.1f}" if isinstance(value,float) else str(value))

def checkpoint(stage:str,**extra)->dict:
    """Log one MEMORY line and flag low system memory (safety guard only)."""
    data=snapshot();data["stage"]=stage
    fields=" ".join(f"{key}={_fmt(data[key])}" for key in ("rss_mb","private_mb","peak_rss_mb","peak_private_mb","handles","threads","available_mb"))
    tail=" ".join(f"{key}={value}" for key,value in extra.items())
    logging.info("MEMORY stage=%s %s%s",stage,fields,(" "+tail) if tail else "")
    available=data.get("available_mb");data["low_memory"]=available is not None and available<float(os.environ.get("MWS_LOW_MEMORY_MB",LOW_AVAILABLE_MB))
    if data["low_memory"]:logging.warning("MEMORY low_available stage=%s available_mb=%.1f threshold_mb=%.1f",stage,available,float(os.environ.get("MWS_LOW_MEMORY_MB",LOW_AVAILABLE_MB)))
    return data

def low_memory_message(data:dict)->str|None:
    if not data.get("low_memory"):return None
    return f"시스템 여유 메모리가 부족합니다 ({data['available_mb']:.0f}MB). 다른 프로그램을 닫아 주세요. 렌더는 계속 진행됩니다."
