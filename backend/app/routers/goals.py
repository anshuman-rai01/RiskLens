"""
FastAPI router for Personal Goals CRUD endpoints with strict user isolation,
progress percentage computation, and soft delete.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.goal import Goal
from app.models.user import User
from app.schemas.goal import (
    GoalCreate,
    GoalListResponse,
    GoalResponse,
    GoalUpdate,
)

router = APIRouter(prefix="/goals", tags=["goals"])


# ==============================================================================
# ISOLATION PRINCIPLE ENFORCEMENT:
#
# Every database query in this module explicitly filters by:
#   1. Goal.user_id == current_user.id (ensuring users can never access or modify
#      goals belonging to another user)
#   2. Goal.deleted_at.is_(None) (ensuring soft-deleted goals remain invisible
#      to all normal API read/write operations)
#
# Attempting to access a goal that does not exist or belongs to another user
# returns HTTP 404 Not Found to prevent resource enumeration.
# ==============================================================================


@router.post(
    "",
    response_model=GoalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new goal",
)
async def create_goal(
    payload: GoalCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GoalResponse:
    """
    Create a new personal target goal for the authenticated user.
    current_value defaults to 0.00 if omitted, or takes the supplied initial progress.
    """
    goal = Goal(
        user_id=current_user.id,
        name=payload.name,
        target_value=payload.target_value,
        current_value=payload.current_value,
        unit=payload.unit,
        deadline=payload.deadline,
    )
    db.add(goal)
    await db.commit()
    await db.refresh(goal)
    return GoalResponse.from_orm_with_computed(goal)


@router.get(
    "",
    response_model=GoalListResponse,
    summary="List and filter goals",
)
async def list_goals(
    include_completed: bool = Query(True, description="Whether to include completed goals"),
    limit: int = Query(50, ge=1, le=200, description="Max goals to return"),
    offset: int = Query(0, ge=0, description="Number of goals to skip"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GoalListResponse:
    """
    List goals for the authenticated user.
    Sort order:
      1. Incomplete goals first, ordered by deadline ascending (nulls last)
      2. Completed goals last, ordered by deadline ascending (nulls last)
      3. Newest created goals as tiebreakers
    """
    base_conditions = [
        Goal.user_id == current_user.id,
        Goal.deleted_at.is_(None),
    ]

    if not include_completed:
        base_conditions.append(Goal.current_value < Goal.target_value)

    # Total count matching filters
    count_stmt = select(func.count()).select_from(Goal).where(*base_conditions)
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    # Sort: incomplete (0) before completed (1), then deadline ASC NULLS LAST, created_at DESC
    is_completed_expr = case(
        (Goal.current_value >= Goal.target_value, 1),
        else_=0,
    )

    items_stmt = (
        select(Goal)
        .where(*base_conditions)
        .order_by(
            is_completed_expr.asc(),
            Goal.deadline.asc().nulls_last(),
            Goal.created_at.desc(),
        )
        .limit(limit)
        .offset(offset)
    )
    items_result = await db.execute(items_stmt)
    items = list(items_result.scalars().all())

    return GoalListResponse(
        items=[GoalResponse.from_orm_with_computed(g) for g in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{goal_id}",
    response_model=GoalResponse,
    summary="Get single goal by ID",
)
async def get_goal(
    goal_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GoalResponse:
    """Retrieve a single goal by ID if owned by authenticated user and not deleted."""
    stmt = select(Goal).where(
        Goal.id == goal_id,
        Goal.user_id == current_user.id,
        Goal.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    goal = result.scalar_one_or_none()

    if goal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Goal not found",
        )

    return GoalResponse.from_orm_with_computed(goal)


@router.put(
    "/{goal_id}",
    response_model=GoalResponse,
    summary="Update an existing goal",
)
async def update_goal(
    goal_id: uuid.UUID,
    payload: GoalUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GoalResponse:
    """
    Update target_value, current_value, name, unit, or deadline of a goal.
    Updating current_value is the primary mechanism for logging goal progress.
    """
    stmt = select(Goal).where(
        Goal.id == goal_id,
        Goal.user_id == current_user.id,
        Goal.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    goal = result.scalar_one_or_none()

    if goal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Goal not found",
        )

    update_data = payload.model_dump(exclude_unset=True)

    if update_data:
        for field, value in update_data.items():
            setattr(goal, field, value)
        goal.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(goal)

    return GoalResponse.from_orm_with_computed(goal)


@router.delete(
    "/{goal_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft delete a goal",
)
async def delete_goal(
    goal_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Soft-delete a goal by setting deleted_at timestamp.
    Returns 404 if the goal does not exist, belongs to another user,
    or was already deleted.
    """
    stmt = select(Goal).where(
        Goal.id == goal_id,
        Goal.user_id == current_user.id,
        Goal.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    goal = result.scalar_one_or_none()

    if goal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Goal not found",
        )

    goal.deleted_at = datetime.now(timezone.utc)
    await db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)
