"""
Recommendation engine — simulation-specific orchestrator for AI recommendations.

This is the bridge between the generic grounded_llm service and the simulation
domain. It:
1. Summarizes chart line data (first/last/midpoint + trend direction)
2. Computes additional context (e.g., total expenses for savings_rate)
3. Selects the correct system prompt variant
4. Calls grounded_llm.generate_grounded_recommendation()
5. Updates the cached SimulationResult row with results

The grounded_llm module remains fully domain-agnostic — this module
is the only place where simulation-specific knowledge lives.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session
from app.models.entry import Entry
from app.models.simulation import SimulationResult
from app.schemas.recommendation import RecommendationResponse
from app.services.grounded_llm import generate_grounded_recommendation

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# SYSTEM PROMPT TEMPLATES
# ═══════════════════════════════════════════════════════════════════════

BASE_GROUNDING_RULES = """\
You are RiskLens AI, an objective analytical recommendation engine for scenario simulations.

GROUNDING RULES (STRICT AND NON-NEGOTIABLE):
1. Base your response ONLY on the numbers provided in the context below. Do not invent, estimate, or assume any figure not given to you.
2. If a specific metric, percentage, or number is not in the context, do not mention or extrapolate it.
3. Every recommendation must be directly grounded in one or more specific numbers present in the context.
4. Output must strictly conform to the requested JSON schema containing between 2 and 4 recommendations.
5. Each recommendation must have:
   - title: concise, actionable summary (max 10 words)
   - impact: "High", "Medium", or "Low"
   - effort: "High", "Medium", or "Low"
   - description: 1-3 sentences explaining the recommendation, citing only numbers from the context.\
"""

SAVINGS_RATE_PROMPT = BASE_GROUNDING_RULES + """

SCENARIO SPECIFIC RULES — INCREASE SAVINGS RATE:
1. You are analyzing an Increase Savings Rate simulation based on the user's historical tracked income and savings, and computed expense totals.
2. STRICT PROHIBITIONS:
   - DO NOT invent or propose any "optimal savings rate" or target percentage other than the user's selected target_rate and computed current_rate provided in the context.
   - DO NOT name or recommend any specific financial products or instruments (e.g., do NOT mention LIC, specific mutual funds, fixed deposit schemes, individual banks, ETFs, crypto, or specific investment products).
3. Keep all recommendations generic, behavioral, and operational (e.g., suggest automated recurring transfers, auditing discretionary expenses, or aligning savings transfers with income deposit schedules).
4. You may reference the computed total expenses, current rate, target rate, and projected cumulative savings difference provided in the context.
5. Required Disclaimer: You MUST populate the disclaimer field with the exact text:
   "General guidance based on your data — not financial advice"
"""

STANDARD_DATA_DRIVEN_PROMPT_TEMPLATE = BASE_GROUNDING_RULES + """

SCENARIO SPECIFIC RULES:
1. You are analyzing a tracked personal simulation for {scenario_type_human}.
2. Base all observations strictly on the provided current metrics, target goals, projected trajectory points, and statistical indicators (such as reliability tier and correlation metrics if present).
3. Do not assume or suggest clinical, medical, or formal educational interventions. Frame recommendations around schedule consistency, incremental habit adjustments, and workload pacing supported directly by the numbers.
"""

HYPOTHETICAL_FRAMING_PROMPT = BASE_GROUNDING_RULES + """

SCENARIO SPECIFIC RULES — HYPOTHETICAL WHAT-IF SIMULATION:
1. These numbers reflect the user's own stated hypothetical inputs and assumptions, NOT real tracked historical behavior.
2. Frame all observations and recommendations strictly as analysis of a hypothetical "what-if" model they configured.
3. DO NOT phrase recommendations as commentary on their actual personal financial habits, real-life spending, or historical discipline.
4. Focus recommendations on sensitivity analysis, testing alternative assumption parameters (e.g., changes in appreciation rate, tuition cost, loan term, or rent growth rate), and stress-testing the model's break-even or net payoff horizon using only the numbers in the context.
"""

# Map scenario types to their prompt variants
SCENARIO_TYPE_LABELS = {
    "increase_savings_rate": "Increase Savings Rate",
    "fitness_plan": "Fitness Plan",
    "reduce_study_hours": "Reduce Study Hours",
    "buy_vs_rent": "Buy vs Rent",
    "program_outcome": "Program Outcome",
}

HYPOTHETICAL_SCENARIOS = {"buy_vs_rent", "program_outcome"}
SAVINGS_RATE_SCENARIO = "increase_savings_rate"


def _get_system_prompt(scenario_type: str) -> str:
    """Select the correct system prompt variant for a scenario type."""
    if scenario_type == SAVINGS_RATE_SCENARIO:
        return SAVINGS_RATE_PROMPT
    elif scenario_type in HYPOTHETICAL_SCENARIOS:
        return HYPOTHETICAL_FRAMING_PROMPT
    else:
        human_label = SCENARIO_TYPE_LABELS.get(scenario_type, scenario_type)
        return STANDARD_DATA_DRIVEN_PROMPT_TEMPLATE.format(
            scenario_type_human=human_label,
        )


def _summarize_chart_lines(lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Summarize chart line data for the LLM context.

    Instead of sending all 60+ points, send first/last/midpoint values
    plus overall trend direction. This keeps the context compact while
    providing enough grounding data.
    """
    summarized = []
    for line in lines:
        points = line.get("points", [])
        if not points:
            summarized.append({
                "label": line.get("label", "unknown"),
                "summary": "no data points",
            })
            continue

        first_val = points[0].get("value", 0)
        last_val = points[-1].get("value", 0)
        mid_idx = len(points) // 2
        mid_val = points[mid_idx].get("value", 0)

        if last_val > first_val * 1.05:
            trend = "increasing"
        elif last_val < first_val * 0.95:
            trend = "decreasing"
        else:
            trend = "stable"

        summarized.append({
            "label": line.get("label", "unknown"),
            "first_date": points[0].get("date"),
            "first_value": round(first_val, 2),
            "midpoint_date": points[mid_idx].get("date"),
            "midpoint_value": round(mid_val, 2),
            "last_date": points[-1].get("date"),
            "last_value": round(last_val, 2),
            "total_points": len(points),
            "trend": trend,
        })

    return summarized


async def _compute_total_expenses(
    user_id: uuid.UUID,
    db: AsyncSession,
) -> Optional[float]:
    """
    Compute total expenses from income_expense entries tagged as 'expense'.
    Uses the same notes-field tagging convention established in Chunk 9.
    """
    stmt = (
        select(Entry)
        .where(
            Entry.user_id == user_id,
            Entry.category == "income_expense",
            Entry.deleted_at.is_(None),
        )
    )
    result = await db.execute(stmt)
    entries = result.scalars().all()

    expense_total = 0.0
    for entry in entries:
        notes = (entry.notes or "").strip().lower()
        if notes == "expense":
            expense_total += float(entry.value)

    return round(expense_total, 2) if expense_total > 0 else None


def _build_context(
    sim: SimulationResult,
    total_expenses: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Build the grounding context dict from a SimulationResult.

    Only includes already-computed simulation output — never raw entries.
    """
    result_data = sim.result_data or {}

    context: Dict[str, Any] = {
        "scenario_type": sim.scenario_type,
        "input_params": sim.input_params,
        "reliability": sim.reliability,
        "message": sim.message,
        "derived_values": result_data.get("derived_values"),
    }

    # Summarize chart lines instead of sending all points
    lines = result_data.get("lines", [])
    if lines:
        context["chart_trajectory_summary"] = _summarize_chart_lines(lines)

    # Add correlation data if present (reduce_study_hours)
    r_squared = result_data.get("correlation_r_squared")
    if r_squared is not None:
        context["correlation_r_squared"] = r_squared

    # Add total expenses for savings_rate scenario
    if total_expenses is not None:
        context["total_tracked_expenses"] = total_expenses

    return context


async def generate_recommendations_for_simulation(
    simulation_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    """
    Background task: generate AI recommendations for a cached simulation.

    Opens its own DB session (BackgroundTasks run after the response is sent,
    so the request's session is closed). Updates the SimulationResult row
    in-place with the results.
    """
    async with async_session() as db:
        try:
            # Fetch the simulation result
            stmt = select(SimulationResult).where(
                SimulationResult.id == simulation_id,
                SimulationResult.user_id == user_id,
            )
            sim = (await db.execute(stmt)).scalar_one_or_none()

            if sim is None:
                logger.error(
                    "Recommendation engine: simulation %s not found for user %s",
                    simulation_id, user_id,
                )
                return

            # If status is no longer "pending", another task already handled it
            if sim.recommendations_status != "pending":
                logger.info(
                    "Recommendation engine: simulation %s already has status '%s', skipping",
                    simulation_id, sim.recommendations_status,
                )
                return

            scenario_type = sim.scenario_type

            # Compute additional context for savings_rate
            total_expenses = None
            if scenario_type == SAVINGS_RATE_SCENARIO:
                total_expenses = await _compute_total_expenses(user_id, db)

            # Build context and prompt
            context = _build_context(sim, total_expenses=total_expenses)
            system_prompt = _get_system_prompt(scenario_type)

            # Call the generic grounded LLM service
            result, outcome = await generate_grounded_recommendation(
                context=context,
                system_prompt=system_prompt,
                response_schema=RecommendationResponse,
                timeout_seconds=15,
                api_key=settings.GEMINI_API_KEY,
                model=settings.GEMINI_MODEL,
            )

            if result is not None:
                # Success — store validated recommendations
                sim.recommendations = [
                    item.model_dump() for item in result.recommendations
                ]
                sim.recommendations_status = "ready"
                sim.recommendation_disclaimer = result.disclaimer
                logger.info(
                    "Recommendation engine: stored %d recommendations for simulation %s",
                    len(result.recommendations), simulation_id,
                )
            else:
                # Failure — degrade gracefully
                sim.recommendations = None
                sim.recommendations_status = "unavailable"
                sim.recommendation_disclaimer = None
                logger.warning(
                    "Recommendation engine: generation failed for simulation %s (outcome=%s)",
                    simulation_id, outcome,
                )

            await db.commit()

        except Exception:
            logger.error(
                "Recommendation engine: unexpected error for simulation %s",
                simulation_id,
                exc_info=True,
            )
            # Attempt to mark as unavailable even on unexpected errors
            try:
                if sim is not None:
                    sim.recommendations = None
                    sim.recommendations_status = "unavailable"
                    sim.recommendation_disclaimer = None
                    await db.commit()
            except Exception:
                logger.error(
                    "Recommendation engine: failed to mark simulation %s as unavailable",
                    simulation_id,
                    exc_info=True,
                )
