"""
Shared scenario architecture: ABC base classes and scenario registry.

Pattern: ABC + Registry Dict
- ABC with @abstractmethod enforces compute() at class definition time (fail-fast)
- Registry dict provides single-lookup dispatch (no if/elif chain)
- Two natural categories: DataDrivenScenario (Prophet-based) and
  AssumptionBasedScenario (perturbation-based, Chunk 10)

Staleness Scope:
- "all" (default for data-driven): cache invalidated when any entry changes
- specific category name (e.g. "savings"): invalidated only when entries
  in that category change
- None: cache indefinitely (no real data dependency)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union

from app.models.entry import Entry


class DataDrivenScenario(ABC):
    """
    Scenarios whose projections are driven by the user's real historical entries.

    Note: Historically, all DataDrivenScenarios were designed to call Prophet's
    compute_forecast(). However, Scenario 1 (IncreaseSavingsRate) and Scenario 2
    (FitnessPlan) deliberately deviate from Prophet because their product specifications
    mandate deterministic mathematical formulas (cumulative wealth projections from
    current savings rate and square-root-of-time variability bands) rather than Prophet's
    generalized additive time-series models.
    """

    # Default staleness scope: invalidate when *any* entry changes
    staleness_scope: Optional[str] = "all"

    @abstractmethod
    def compute(
        self,
        user_id: str,
        entries: List[Entry],
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Compute the simulation result.

        Returns a dict with keys:
            - lines: List[dict] — chart lines
            - reliability: str
            - data_point_count: int
            - message: Optional[str]
            - derived_values: Optional[dict]
            - correlation_r_squared: Optional[float]
        """
        ...


class AssumptionBasedScenario(ABC):
    """
    Scenarios whose Best/Expected/Risk projections come from perturbing
    user-stated assumptions (e.g., interest rates, rent growth).

    Uniform interface: compute(user_id, entries, params) — same signature
    as DataDrivenScenario. Scenarios that don't need real data simply
    ignore the entries parameter.
    """

    # Default staleness scope for assumption-based: no real data dependency
    # Override per-scenario: "savings" for BuyVsRent, None for ProgramOutcome
    staleness_scope: Optional[str] = None

    @abstractmethod
    def compute(
        self,
        user_id: str,
        entries: List[Entry],
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Compute the simulation result.

        Returns the same dict shape as DataDrivenScenario.compute().
        """
        ...


# ── Scenario Registry ────────────────────────────────────────────────
# Populated after concrete scenario classes are defined (below imports).
# The router indexes into this dict with a single registry.get() call.
SCENARIO_REGISTRY: Dict[str, Union[DataDrivenScenario, AssumptionBasedScenario]] = {}


def register_scenarios() -> None:
    """
    Import and register all concrete scenario implementations.
    Called once at module load time.
    """
    from app.services.scenarios.savings_rate import IncreaseSavingsRate
    from app.services.scenarios.fitness_plan import FitnessPlan
    from app.services.scenarios.study_hours import ReduceStudyHours
    from app.services.scenarios.buy_vs_rent import BuyVsRent
    from app.services.scenarios.program_outcome import ProgramOutcome

    SCENARIO_REGISTRY["increase_savings_rate"] = IncreaseSavingsRate()
    SCENARIO_REGISTRY["fitness_plan"] = FitnessPlan()
    SCENARIO_REGISTRY["reduce_study_hours"] = ReduceStudyHours()
    SCENARIO_REGISTRY["buy_vs_rent"] = BuyVsRent()
    SCENARIO_REGISTRY["program_outcome"] = ProgramOutcome()


# Register on import
register_scenarios()
