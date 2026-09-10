"""Cleanup planning and the safety layer that governs it.

Destructive execution is deliberately absent in this milestone: the modules
here only describe and *validate* proposed work.
"""

from spaceai.cleanup.safety import SafetyPolicy, container_roots, protected_roots

__all__ = ["SafetyPolicy", "container_roots", "protected_roots"]
