"""Scheduling metadata for one player command."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CommandSpec:
    """Priority and minimum commitment duration of a command."""

    priority: int
    commitment: float


__all__ = ("CommandSpec",)
