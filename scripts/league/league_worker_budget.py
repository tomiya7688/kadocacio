"""CPU and memory budgeting for concurrent league match workers."""

from __future__ import annotations

import os

from scripts.core.performance_settings import limited_worker_count
from scripts.league.windows_memory_status import WindowsMemoryStatus


def available_memory_bytes() -> int:
    """Return best-effort available physical memory without dependencies."""
    if os.name == "nt":
        try:
            import ctypes

            status = WindowsMemoryStatus()
            status.length = ctypes.sizeof(WindowsMemoryStatus)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.available_physical)
        except (AttributeError, OSError, TypeError):
            pass
    try:
        return int(os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE"))
    except (AttributeError, OSError, ValueError):
        return 4 * 1024**3


def recommended_worker_count(
    task_count: int,
    *,
    reserve_for_ui: bool = True,
    cpu_limit_percent: int = 100,
    available_memory: int | None = None,
) -> int:
    """Choose a safe worker count from CPU, memory and task constraints."""
    tasks = max(1, int(task_count))
    logical_cores = max(1, os.cpu_count() or 2)
    estimated_physical = max(1, (logical_cores + 1) // 2)
    cpu_budget = estimated_physical
    if reserve_for_ui and estimated_physical > 2:
        cpu_budget -= 1
    cpu_budget = max(1, min(8, cpu_budget))
    cpu_budget = limited_worker_count(cpu_budget, cpu_limit_percent)
    available = available_memory_bytes() if available_memory is None else max(0, int(available_memory))
    reserve = 1536 * 1024**2
    estimated_per_match = 320 * 1024**2
    memory_budget = max(1, int(max(0, available - reserve) // estimated_per_match))
    return max(1, min(tasks, cpu_budget, memory_budget))


__all__ = ("available_memory_bytes", "recommended_worker_count")
