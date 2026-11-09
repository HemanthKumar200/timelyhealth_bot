import os
import platform
import shutil
import subprocess
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class HardwareProfile:
    cpu_model: str
    logical_cpu_count: int
    physical_cpu_count: int
    memory_gb: float
    gpu_available: bool
    gpu_type: str
    gpu_name: str
    inference_mode: str
    ollama_threads: int
    ollama_num_gpu: int
    recommended_num_ctx: int
    recommended_top_k: int


def get_cpu_model():
    cpu = platform.processor().strip()
    if cpu:
        return cpu
    try:
        if os.name == "nt":
            cpu = os.environ.get("PROCESSOR_IDENTIFIER", "").strip()
            if cpu:
                return cpu
    except Exception:
        pass
    return platform.machine() or "Unknown CPU"


def get_ram_gb():
    try:
        import psutil
        return round(psutil.virtual_memory().total / (1024 ** 3), 1)
    except Exception:
        try:
            if os.name == "nt":
                import ctypes
                class MemoryStatus(ctypes.Structure):
                    _fields_ = [
                        ("length", ctypes.c_ulong),
                        ("memory_load", ctypes.c_ulong),
                        ("total_physical", ctypes.c_ulonglong),
                        ("available_physical", ctypes.c_ulonglong),
                        ("total_page", ctypes.c_ulonglong),
                        ("available_page", ctypes.c_ulonglong),
                        ("total_virtual", ctypes.c_ulonglong),
                        ("available_virtual", ctypes.c_ulonglong),
                        ("extended_virtual", ctypes.c_ulonglong),
                    ]
                status = MemoryStatus()
                status.length = ctypes.sizeof(status)
                ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
                return round(status.total_physical / (1024 ** 3), 1)
        except Exception:
            pass
    return 0.0


def get_gpu_info():
    if shutil.which("nvidia-smi"):
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            name = result.stdout.strip().splitlines()[0].strip() if result.stdout.strip() else ""
            if name:
                return True, "NVIDIA", name
        except Exception:
            pass

    if os.name == "nt":
        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Get-CimInstance Win32_VideoController | "
                    "Select-Object -ExpandProperty Name",
                ],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
            names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
            if names:
                joined = " / ".join(names)
                gpu_type = "AMD" if any("AMD" in n.upper() or "RADEON" in n.upper() for n in names) else "OTHER"
                if gpu_type == "OTHER" and any("NVIDIA" in n.upper() or "GEFORCE" in n.upper() for n in names):
                    gpu_type = "NVIDIA"
                return True, gpu_type, joined
        except Exception:
            pass

    return False, "CPU_ONLY", ""


def detect_hardware_profile():
    try:
        import psutil
        logical = psutil.cpu_count(logical=True) or os.cpu_count() or 2
        physical = psutil.cpu_count(logical=False) or max(1, logical // 2)
    except Exception:
        logical = os.cpu_count() or 2
        physical = max(1, logical // 2)

    memory_gb = get_ram_gb()
    gpu_available, gpu_type, gpu_name = get_gpu_info()

    if memory_gb < 8:
        mode = "low_memory_cpu"
        num_ctx = 2048
        top_k = 3
        num_gpu = 0 if not gpu_available else 20
    elif memory_gb < 16:
        mode = "balanced_cpu" if not gpu_available else "balanced_gpu"
        num_ctx = 3072
        top_k = 4
        num_gpu = 0 if not gpu_available else 35
    else:
        mode = "gpu" if gpu_available else "cpu"
        num_ctx = 4096
        top_k = 5
        num_gpu = 99 if gpu_available else 0

    threads = max(1, min(physical, 8))
    return HardwareProfile(
        cpu_model=get_cpu_model(),
        logical_cpu_count=logical,
        physical_cpu_count=physical,
        memory_gb=memory_gb,
        gpu_available=gpu_available,
        gpu_type=gpu_type,
        gpu_name=gpu_name,
        inference_mode=mode,
        ollama_threads=threads,
        ollama_num_gpu=num_gpu,
        recommended_num_ctx=num_ctx,
        recommended_top_k=top_k,
    )
