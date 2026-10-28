"""Read-only Windows resource telemetry; all sizes are explicit bytes."""
import ctypes as c
from datetime import datetime,timezone
from functools import lru_cache
import os,shutil,time


class ResourceObservationError(RuntimeError):pass


class MemoryStatus(c.Structure):
    _fields_=[('dwLength',c.c_uint32),('dwMemoryLoad',c.c_uint32)]+[(n,c.c_uint64) for n in (
        'ullTotalPhys','ullAvailPhys','ullTotalPageFile','ullAvailPageFile','ullTotalVirtual','ullAvailVirtual','ullAvailExtendedVirtual')]


class PerformanceInfo(c.Structure):
    _fields_=[('cb',c.c_uint32)]+[(n,c.c_size_t) for n in ('CommitTotal','CommitLimit','CommitPeak','PhysicalTotal','PhysicalAvailable',
        'SystemCache','KernelTotal','KernelPaged','KernelNonpaged','PageSize')]+[(n,c.c_uint32) for n in ('HandleCount','ProcessCount','ThreadCount')]


class ProcessInfo(c.Structure):
    _fields_=[('cb',c.c_uint32),('PageFaultCount',c.c_uint32)]+[(n,c.c_size_t) for n in ('PeakWorkingSetSize','WorkingSetSize',
        'QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage')]


def decode(memory,performance,process):
    page=int(performance.PageSize);total=int(performance.CommitTotal);limit=int(performance.CommitLimit)
    if page<=0 or total>limit:raise ResourceObservationError('invalid system commit observation')
    return dict(system_commit_total_bytes=total*page,system_commit_limit_bytes=limit*page,
        system_commit_available_bytes=(limit-total)*page,system_commit_peak_bytes=int(performance.CommitPeak)*page,
        system_commit_total_pages=total,system_commit_limit_pages=limit,system_commit_peak_pages=int(performance.CommitPeak),
        current_process_available_commit_bytes=int(memory.ullAvailPageFile),physical_total_bytes=int(memory.ullTotalPhys),
        physical_available_bytes=int(memory.ullAvailPhys),process_private_commit_bytes=int(process.PrivateUsage),
        process_peak_private_commit_bytes=int(process.PeakPagefileUsage),process_working_set_bytes=int(process.WorkingSetSize),
        process_peak_working_set_bytes=int(process.PeakWorkingSetSize),observer_available_address_space_bytes=int(memory.ullAvailVirtual),page_size_bytes=page)


@lru_cache(None)
def functions():
    if os.name!='nt' or c.sizeof(c.c_void_p)!=8:raise ResourceObservationError('qualified Windows64 telemetry required')
    if (c.sizeof(MemoryStatus),c.sizeof(PerformanceInfo),c.sizeof(ProcessInfo))!=(64,104,80):raise ResourceObservationError('Windows64 structure layout changed')
    kernel=c.WinDLL('kernel32',use_last_error=True);psapi=c.WinDLL('psapi',use_last_error=True)
    kernel.GetCurrentProcess.argtypes=[];kernel.GetCurrentProcess.restype=c.c_void_p
    kernel.GetProcessId.argtypes=[c.c_void_p];kernel.GetProcessId.restype=c.c_uint32
    kernel.GlobalMemoryStatusEx.argtypes=[c.POINTER(MemoryStatus)];kernel.GlobalMemoryStatusEx.restype=c.c_int
    psapi.GetPerformanceInfo.argtypes=[c.POINTER(PerformanceInfo),c.c_uint32];psapi.GetPerformanceInfo.restype=c.c_int
    psapi.GetProcessMemoryInfo.argtypes=[c.c_void_p,c.POINTER(ProcessInfo),c.c_uint32];psapi.GetProcessMemoryInfo.restype=c.c_int
    return kernel,psapi


def snapshot(root,*,process_handle=None,process_id=None):
    start=time.perf_counter_ns();kernel,psapi=functions();memory=MemoryStatus();memory.dwLength=c.sizeof(memory)
    performance=PerformanceInfo();performance.cb=c.sizeof(performance);process=ProcessInfo();process.cb=c.sizeof(process)
    handle=kernel.GetCurrentProcess() if process_handle is None else int(process_handle)
    pid=int(kernel.GetProcessId(handle))
    if not pid:raise ResourceObservationError('GetProcessId failed WinError='+str(c.get_last_error()))
    if process_id is not None and pid!=process_id:raise ResourceObservationError('process handle identity mismatch')
    for name,fn,args in (('GlobalMemoryStatusEx',kernel.GlobalMemoryStatusEx,(c.byref(memory),)),
        ('GetPerformanceInfo',psapi.GetPerformanceInfo,(c.byref(performance),c.sizeof(performance))),
        ('GetProcessMemoryInfo',psapi.GetProcessMemoryInfo,(handle,c.byref(process),c.sizeof(process)))):
        ok=fn(*args)
        if not ok:raise ResourceObservationError(name+' failed WinError='+str(c.get_last_error()))
    values=decode(memory,performance,process)
    # ullAvailPageFile belongs to this calling observer, even when process
    # counters are sampled through an owned child handle. Keep that identity.
    return dict(schema='OCCAM_RESOURCE_SAMPLE_V1',timestamp_UTC=datetime.now(timezone.utc).isoformat(),sample_started_ns=start,
        sample_completed_ns=time.perf_counter_ns(),observer_pid=os.getpid(),measured_process_pid=pid,pointer_bits=64,
        disk_free_bytes=shutil.disk_usage(root).free,**values)


def gate(sample,*,minimum_commit_bytes,minimum_disk_bytes,maximum_private_bytes=None):
    if type(sample) is not dict:raise ResourceObservationError('resource sample unavailable')
    keys=('system_commit_available_bytes','current_process_available_commit_bytes','disk_free_bytes','process_private_commit_bytes')
    if any(type(sample.get(k)) is not int or sample[k]<0 for k in keys):raise ResourceObservationError('resource value unavailable or invalid')
    for n in (minimum_commit_bytes,minimum_disk_bytes):
        if type(n) is not int or n<0:raise ValueError('nonnegative resource threshold')
    if maximum_private_bytes is not None and (type(maximum_private_bytes) is not int or maximum_private_bytes<0):raise ValueError('nonnegative private threshold')
    reasons=[]
    if min(sample[k] for k in keys[:2])<minimum_commit_bytes:reasons.append('AVAILABLE_COMMIT_BELOW_FLOOR')
    if sample['disk_free_bytes']<minimum_disk_bytes:reasons.append('DISK_BELOW_FLOOR')
    if maximum_private_bytes is not None and sample['process_private_commit_bytes']>maximum_private_bytes:reasons.append('OWNED_PROCESS_PRIVATE_COMMIT_ABOVE_CAP')
    return dict(allowed=not reasons,reasons=reasons,minimum_commit_bytes=minimum_commit_bytes,minimum_disk_bytes=minimum_disk_bytes,
        maximum_private_bytes=maximum_private_bytes,volatile_observation_not_memory_reservation=True)
