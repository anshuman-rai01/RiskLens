"""
FastAPI router for simulation scenarios with caching and debug inspection.

Cache staleness is scoped per-scenario:
- staleness_scope == "all": invalidated when any entry changes (data-driven default)
- staleness_scope == specific category: only check entries in that category change
- staleness_scope is None: cache indefinitely (assumption-based, no real data dependency)

Chunk 11 additions:
- BackgroundTask fires AI recommendation generation after response is sent
- Staleness-driven recompute resets recommendations to null/"pending"
- Stuck "pending" rows are detected and re-fired on next request
- GET /simulations/{id} polling endpoint for frontend to pick up ready recommendations
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, Set

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.entry import Entry
from app.models.simulation import SimulationResult
from app.models.user import User
from app.schemas.simulation import (
    BuyVsRentParams,
    FitnessPlanParams,
    IncreaseSavingsRateParams,
    ProgramOutcomeParams,
    ScenarioType,
    SimulationDebugResponse,
    SimulationLine,
    SimulationPoint,
    SimulationRequest,
    SimulationResponse,
    StudyHoursParams,
)
from app.services.scenarios import (
    SCENARIO_REGISTRY,
    AssumptionBasedScenario,
    DataDrivenScenario,
)
from app.services.recommendation_engine import generate_recommendations_for_simulation

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/simulations", tags=["simulations"])

# Map scenario types to their param validation schemas
PARAM_VALIDATORS = {
    "increase_savings_rate": IncreaseSavingsRateParams,
    "fitness_plan": FitnessPlanParams,
    "reduce_study_hours": StudyHoursParams,
    "buy_vs_rent": BuyVsRentParams,
    "program_outcome": ProgramOutcomeParams,
}

# Track active recommendation generation tasks (thread-safe for single-process uvicorn).
# This prevents re-firing a task for a row that's already being processed in a
# BackgroundTask that hasn't completed yet.
_ACTIVE_TASKS: Set[uuid.UUID] = set()


def compute_params_hash(params: dict) -> str:
    """
    Compute a deterministic SHA-256 hash of the params dict.
    sort_keys=True ensures consistent ordering.
    """
    serialized = json.dumps(params, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _fire_recommendation_task(
    background_tasks: BackgroundTasks,
    simulation_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    """
    Enqueue a recommendation generation background task if one isn't
    already active for this simulation.
    """
    if simulation_id in _ACTIVE_TASKS:
        logger.info(
            "Recommendation task already active for simulation %s, skipping",
            simulation_id,
        )
        return

    async def _wrapped_task(sim_id: uuid.UUID, uid: uuid.UUID) -> None:
        _ACTIVE_TASKS.add(sim_id)
        try:
            await generate_recommendations_for_simulation(sim_id, uid)
        finally:
            _ACTIVE_TASKS.discard(sim_id)

    background_tasks.add_task(_wrapped_task, simulation_id, user_id)
    logger.info(
        "Fired recommendation BackgroundTask for simulation %s",
        simulation_id,
    )


# ==============================================================================
# DISPATCH:
#
# A single registry lookup replaces if/elif branching. The scenario_type string
# maps to a concrete scenario instance. Missing scenarios are a 404, not a
# silent fall-through.
#
# Cache key: (user_id, scenario_type, params_hash) — two different target_rate
# values produce two different hashes and two separate cache entries.
#
# Staleness scoping:
# - "all": check all entries for any modification after generated_at
# - specific category string: only check entries in that category
# - None: never stale (assumption-based, no real data dependency)
# ==============================================================================


@router.post(
    "",
    response_model=SimulationResponse,
    status_code=status.HTTP_200_OK,
    summary="Run a simulation scenario",
)
async def run_simulation(
    payload: SimulationRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SimulationResponse:
    """
    Run a simulation scenario. Results are cached by (user_id, scenario_type, params_hash).
    If a cached result exists with the same params, it is returned without recomputation.

    Recommendations are generated asynchronously in a BackgroundTask and are
    initially returned as null with status "pending". Poll GET /simulations/{id}
    to retrieve them once ready.
    """
    scenario_type = payload.scenario_type.value
    params = payload.params

    # ── Validate scenario exists in registry ──────────────────────
    scenario = SCENARIO_REGISTRY.get(scenario_type)
    if scenario is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown scenario type: {scenario_type}. "
                   f"Available: {list(SCENARIO_REGISTRY.keys())}",
        )

    # ── Validate params if a validator schema exists ──────────────
    validator = PARAM_VALIDATORS.get(scenario_type)
    if validator is not None:
        try:
            validator(**params)
        except ValidationError as exc:
            errors = exc.errors()
            detail = [
                {
                    "field": ".".join(str(loc) for loc in err["loc"]),
                    "message": err["msg"],
                    "type": err["type"],
                }
                for err in errors
            ]
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=detail,
            )

    # ── Compute params hash for cache key ─────────────────────────
    params_hash = compute_params_hash(params)

    # ── Check for cached result ───────────────────────────────────
    cache_stmt = select(SimulationResult).where(
        SimulationResult.user_id == current_user.id,
        SimulationResult.scenario_type == scenario_type,
        SimulationResult.params_hash == params_hash,
    )
    cached = (await db.execute(cache_stmt)).scalar_one_or_none()

    # Check if cache is still fresh, scoped by scenario's staleness_scope
    if cached is not None:
        scope = scenario.staleness_scope

        if scope is None:
            # Indefinite cache — never stale (ProgramOutcome)
            logger.info(
                "Simulation cache HIT (indefinite): user=%s, scenario=%s, hash=%s",
                current_user.id, scenario_type, params_hash[:12],
            )
            # Check for stuck "pending" recommendations and re-fire if needed
            if (
                cached.recommendations_status == "pending"
                and cached.id not in _ACTIVE_TASKS
            ):
                _fire_recommendation_task(
                    background_tasks, cached.id, current_user.id,
                )
            return _build_response(cached)

        # Build staleness query
        stale_conditions = [
            Entry.user_id == current_user.id,
            Entry.deleted_at.is_(None) | Entry.deleted_at.isnot(None),  # all entries
            (
                (Entry.created_at > cached.generated_at)
                | (Entry.updated_at > cached.generated_at)
                | (Entry.deleted_at > cached.generated_at)
            ),
        ]

        # Apply category scope filter if not "all"
        if scope != "all":
            stale_conditions.append(Entry.category == scope)

        stale_check = select(Entry).where(*stale_conditions).limit(1)
        stale_entry = (await db.execute(stale_check)).scalar_one_or_none()

        if stale_entry is None:
            logger.info(
                "Simulation cache HIT (scope=%s): user=%s, scenario=%s, hash=%s",
                scope, current_user.id, scenario_type, params_hash[:12],
            )
            # Check for stuck "pending" recommendations and re-fire if needed
            if (
                cached.recommendations_status == "pending"
                and cached.id not in _ACTIVE_TASKS
            ):
                _fire_recommendation_task(
                    background_tasks, cached.id, current_user.id,
                )
            return _build_response(cached)

    # ── Fetch entries and compute ─────────────────────────────────
    logger.info(
        "Simulation cache MISS: computing user=%s, scenario=%s",
        current_user.id, scenario_type,
    )

    entries_stmt = (
        select(Entry)
        .where(
            Entry.user_id == current_user.id,
            Entry.deleted_at.is_(None),
        )
        .order_by(Entry.occurred_at.asc())
    )
    entries = list((await db.execute(entries_stmt)).scalars().all())

    # ── Uniform dispatch to scenario ──────────────────────────────
    result = scenario.compute(
        user_id=str(current_user.id),
        entries=entries,
        params=params,
    )

    now_utc = datetime.now(timezone.utc)

    # ── Store/update cache ────────────────────────────────────────
    # On recompute (cache miss or staleness), ALWAYS reset recommendations
    # to null/"pending" — never leave old recommendations attached to
    # newly recomputed numbers.
    if cached is not None:
        cached.generated_at = now_utc
        cached.input_params = params
        cached.result_data = result
        cached.data_point_count = result.get("data_point_count")
        cached.reliability = result.get("reliability", "insufficient")
        cached.message = result.get("message")
        # Reset recommendations for fresh generation
        cached.recommendations = None
        cached.recommendations_status = "pending"
        cached.recommendation_disclaimer = None
    else:
        cached = SimulationResult(
            user_id=current_user.id,
            scenario_type=scenario_type,
            params_hash=params_hash,
            input_params=params,
            generated_at=now_utc,
            result_data=result,
            data_point_count=result.get("data_point_count"),
            reliability=result.get("reliability", "insufficient"),
            message=result.get("message"),
            recommendations=None,
            recommendations_status="pending",
            recommendation_disclaimer=None,
        )
        db.add(cached)

    await db.commit()
    await db.refresh(cached)

    # Fire recommendation generation as a BackgroundTask
    _fire_recommendation_task(background_tasks, cached.id, current_user.id)

    return _build_response(cached)


@router.get(
    "/{simulation_id}",
    response_model=SimulationResponse,
    summary="Poll a simulation result (including recommendation status)",
)
async def get_simulation(
    simulation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SimulationResponse:
    """
    Retrieve a cached simulation result by ID. This is the polling endpoint
    the frontend uses to pick up recommendations once they transition from
    "pending" to "ready" or "unavailable".
    """
    stmt = select(SimulationResult).where(
        SimulationResult.id == simulation_id,
        SimulationResult.user_id == current_user.id,
    )
    sim = (await db.execute(stmt)).scalar_one_or_none()

    if sim is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Simulation result not found",
        )

    return _build_response(sim)


@router.get(
    "/{simulation_id}/debug",
    response_model=SimulationDebugResponse,
    summary="Debug/inspect a cached simulation result",
)
async def debug_simulation(
    simulation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SimulationDebugResponse:
    """
    Return debug/inspection data for a cached simulation result.
    Authenticated and isolated by user_id — a user can only inspect their own simulations.

    Returns: generated_at, params_hash, raw input_params, data_point_count,
    reliability, scenario-specific derived intermediate values,
    recommendations_status, and a sanitized recommendation outcome indicator.
    """
    stmt = select(SimulationResult).where(
        SimulationResult.id == simulation_id,
        SimulationResult.user_id == current_user.id,
    )
    sim = (await db.execute(stmt)).scalar_one_or_none()

    if sim is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Simulation result not found",
        )

    result_data = sim.result_data or {}

    # Derive a sanitized outcome indicator from the current state
    rec_outcome = None
    if sim.recommendations_status == "ready":
        rec_outcome = "success"
    elif sim.recommendations_status == "unavailable":
        rec_outcome = "generation_failed"
    elif sim.recommendations_status == "pending":
        rec_outcome = "in_progress" if sim.id in _ACTIVE_TASKS else "awaiting_task"

    return SimulationDebugResponse(
        id=str(sim.id),
        scenario_type=sim.scenario_type,
        generated_at=sim.generated_at,
        params_hash=sim.params_hash,
        input_params=sim.input_params,
        data_point_count=sim.data_point_count,
        reliability=sim.reliability,
        derived_values=result_data.get("derived_values"),
        recommendations_status=sim.recommendations_status,
        recommendation_outcome=rec_outcome,
    )


def _build_response(sim: SimulationResult) -> SimulationResponse:
    """Build a SimulationResponse from a cached SimulationResult model."""
    result_data = sim.result_data or {}

    lines = []
    for line_data in result_data.get("lines", []):
        points = [
            SimulationPoint(date=p["date"], value=p["value"])
            for p in line_data.get("points", [])
        ]
        lines.append(SimulationLine(label=line_data["label"], points=points))

    return SimulationResponse(
        id=str(sim.id),
        scenario_type=sim.scenario_type,
        reliability=sim.reliability,
        data_point_count=sim.data_point_count,
        message=sim.message,
        lines=lines,
        generated_at=sim.generated_at,
        correlation_r_squared=result_data.get("correlation_r_squared"),
        derived_values=result_data.get("derived_values"),
        recommendations=sim.recommendations,
        recommendations_status=sim.recommendations_status,
        recommendation_disclaimer=sim.recommendation_disclaimer,
    )
