"""
FastAPI router for Entries CRUD endpoints with strict user isolation and soft delete.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.entry import Entry
from app.models.forecast import Forecast
from app.models.user import User
from app.schemas.entry import (
    EntryCategory,
    EntryCreate,
    EntryListResponse,
    EntryResponse,
    EntryUpdate,
    format_entry_value,
)

router = APIRouter(prefix="/entries", tags=["entries"])


# ==============================================================================
# ISOLATION PRINCIPLE ENFORCEMENT:
#
# Every database query in this module explicitly filters by:
#   1. Entry.user_id == current_user.id (ensuring users can never access or modify
#      records belonging to another user)
#   2. Entry.deleted_at.is_(None) (ensuring soft-deleted records remain invisible
#      to all normal API read/write operations)
#
# Attempting to access an entry that does not exist or belongs to another user
# returns HTTP 404 Not Found to prevent resource enumeration.
# ==============================================================================


@router.post(
    "",
    response_model=EntryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new entry",
)
async def create_entry(
    payload: EntryCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Entry:
    """Create a new time-series entry owned by the authenticated user."""
    notes = payload.notes
    if payload.category == EntryCategory.FITNESS:
        if payload.intensity:
            notes = payload.intensity.strip().lower()
        elif not notes:
            notes = "moderate"
    elif payload.intensity and not notes:
        notes = payload.intensity

    entry = Entry(
        user_id=current_user.id,
        category=payload.category.value,
        subcategory=payload.subcategory,
        value=payload.value,
        unit=payload.unit,
        max_value=payload.max_value,
        occurred_at=payload.occurred_at,
        notes=notes,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


@router.get(
    "",
    response_model=EntryListResponse,
    summary="List and filter entries",
)
async def list_entries(
    category: Optional[EntryCategory] = None,
    subcategory: Optional[str] = None,
    from_date: Optional[date] = Query(None, alias="from", description="Filter from date (YYYY-MM-DD) inclusive"),
    to_date: Optional[date] = Query(None, alias="to", description="Filter to date (YYYY-MM-DD) inclusive"),
    limit: int = Query(50, ge=1, le=200, description="Max entries to return"),
    offset: int = Query(0, ge=0, description="Number of entries to skip"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EntryListResponse:
    """
    List entries for the authenticated user, optionally filtered by category,
    subcategory, and date range. Results are ordered newest to oldest by occurred_at.
    """
    base_conditions = [
        Entry.user_id == current_user.id,
        Entry.deleted_at.is_(None),
    ]

    if category is not None:
        base_conditions.append(Entry.category == category.value)
    if subcategory is not None:
        base_conditions.append(Entry.subcategory == subcategory.strip())
    if from_date is not None:
        base_conditions.append(Entry.occurred_at >= from_date)
    if to_date is not None:
        base_conditions.append(Entry.occurred_at <= to_date)

    # Total count matching filters
    count_stmt = select(func.count()).select_from(Entry).where(*base_conditions)
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    # Paginated records
    items_stmt = (
        select(Entry)
        .where(*base_conditions)
        .order_by(Entry.occurred_at.desc(), Entry.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    items_result = await db.execute(items_stmt)
    items = list(items_result.scalars().all())

    return EntryListResponse(
        items=[EntryResponse.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{entry_id}",
    response_model=EntryResponse,
    summary="Get single entry by ID",
)
async def get_entry(
    entry_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Entry:
    """Retrieve a single entry by ID if owned by authenticated user and not deleted."""
    stmt = select(Entry).where(
        Entry.id == entry_id,
        Entry.user_id == current_user.id,
        Entry.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    entry = result.scalar_one_or_none()

    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entry not found",
        )

    return entry


@router.put(
    "/{entry_id}",
    response_model=EntryResponse,
    summary="Update an existing entry",
)
async def update_entry(
    entry_id: uuid.UUID,
    payload: EntryUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Entry:
    """
    Update editable fields of an existing entry.
    Category is immutable. Subcategory (the user-facing label) is editable.
    """
    stmt = select(Entry).where(
        Entry.id == entry_id,
        Entry.user_id == current_user.id,
        Entry.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    entry = result.scalar_one_or_none()

    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entry not found",
        )

    update_data = payload.model_dump(exclude_unset=True)

    if not update_data:
        # Nothing changed
        return entry

    # Forecasts are cached per (user, category, subcategory) and the staleness check
    # only looks at entries that CURRENTLY belong to a series. An entry that moves out
    # of a series would leave that series' cache looking fresh while still containing
    # the moved point, so drop the old series' cache; it is rebuilt on the next request.
    old_subcategory = entry.subcategory
    subcategory_changed = (
        "subcategory" in update_data and update_data["subcategory"] != old_subcategory
    )

    for field, value in update_data.items():
        setattr(entry, field, value)

    if subcategory_changed:
        await db.execute(
            delete(Forecast).where(
                Forecast.user_id == current_user.id,
                Forecast.category == entry.category,
                Forecast.subcategory == old_subcategory
                if old_subcategory is not None
                else Forecast.subcategory.is_(None),
            )
        )

    # Apply category-aware value formatting if value was updated
    if "value" in update_data and entry.value is not None:
        entry.value = format_entry_value(entry.category, entry.value)

    entry.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(entry)
    return entry


@router.delete(
    "/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft delete an entry",
)
async def delete_entry(
    entry_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Soft-delete an entry by setting deleted_at timestamp.
    Returns 404 if the entry does not exist, belongs to another user,
    or was already deleted.
    """
    stmt = select(Entry).where(
        Entry.id == entry_id,
        Entry.user_id == current_user.id,
        Entry.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    entry = result.scalar_one_or_none()

    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entry not found",
        )

    entry.deleted_at = datetime.now(timezone.utc)
    # Invalidate cached forecasts for this user and category
    await db.execute(
        delete(Forecast).where(
            Forecast.user_id == current_user.id,
            Forecast.category == entry.category,
        )
    )
    await db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)
