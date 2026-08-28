from __future__ import annotations

import subprocess

_CUDA_DRIVER_MAJOR_MIN = 560


def detect_accelerator() -> str:
    return "cuda" if _usable_nvidia_cuda() else "cpu"


def _usable_nvidia_cuda() -> bool:
    try:
        completed = subprocess.run(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except OSError, subprocess.TimeoutExpired:
        return False
    if completed.returncode != 0:
        return False
    for line in completed.stdout.splitlines():
        major = line.strip().split(".", 1)[0]
        if major.isdigit() and int(major) >= _CUDA_DRIVER_MAJOR_MIN:
            return True
    return False
