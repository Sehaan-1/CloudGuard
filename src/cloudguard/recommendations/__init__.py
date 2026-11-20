from __future__ import annotations

from cloudguard.recommendations.engine import RecommendationEngine
from cloudguard.recommendations.estimator import SavingsEstimator
from cloudguard.recommendations.rules import (
    IdleVMRule,
    OldSnapshotRule,
    OptimizationRule,
    OrphanedDiskRule,
    OrphanedIPRule,
    OversizedVMRule,
    ReservedInstanceRule,
    StorageClassRule,
    UntaggedResourceRule,
)

__all__ = [
    "IdleVMRule",
    "OldSnapshotRule",
    "OptimizationRule",
    "OrphanedDiskRule",
    "OrphanedIPRule",
    "OversizedVMRule",
    "RecommendationEngine",
    "ReservedInstanceRule",
    "SavingsEstimator",
    "StorageClassRule",
    "UntaggedResourceRule",
]
