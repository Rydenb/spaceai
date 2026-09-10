"""Structured models shared across SpaceAI."""

from spaceai.models.analysis import Category, CategoryUsage, FinderResult
from spaceai.models.cleanup import CleanupAction, RiskLevel, SafetyVerdict
from spaceai.models.disk import DirEntry, DiskUsage, FileEntry, ScanResult, Volume

__all__ = [
    "Category",
    "CategoryUsage",
    "CleanupAction",
    "DirEntry",
    "DiskUsage",
    "FileEntry",
    "FinderResult",
    "RiskLevel",
    "SafetyVerdict",
    "ScanResult",
    "Volume",
]
