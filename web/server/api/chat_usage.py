"""Chat usage tracking: rate limiting, logging, and cost recording."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from flyfun_common.costs import record_cost

from db.models import AnonChatUsageRow, ChatUsageRow

logger = logging.getLogger(__name__)

DAILY_CHAT_LIMIT = 20  # messages per day (free tier)
ANON_DAILY_LIMIT = 3   # anonymous trial queries per day
ANON_COOKIE_NAME = "flyfun_anon"


def _today_start() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def get_today_chat_count(db: Session, user_id: str) -> int:
    """Count chat messages sent today by user."""
    return (
        db.query(func.count())
        .select_from(ChatUsageRow)
        .filter(
            ChatUsageRow.user_id == user_id,
            ChatUsageRow.timestamp >= _today_start(),
        )
        .scalar()
    ) or 0


def check_chat_rate_limit(db: Session, user_id: str) -> None:
    """Raise 429 if daily chat limit is exceeded."""
    count = get_today_chat_count(db, user_id)
    if count >= DAILY_CHAT_LIMIT:
        raise HTTPException(
            status_code=429,
            detail=f"Daily chat limit reached ({DAILY_CHAT_LIMIT} messages/day). Try again tomorrow.",
        )


def log_chat_usage(
    db: Session,
    user_id: str,
    *,
    model: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cost_usd: float = 0.0,
    thread_id: str | None = None,
    persona_id: str | None = None,
) -> int:
    """Log a chat interaction and record cost in shared ledger.

    Returns the ChatUsageRow id.
    """
    row = ChatUsageRow(
        user_id=user_id,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        thread_id=thread_id,
        persona_id=persona_id,
    )
    db.add(row)
    db.flush()

    # Record in shared cost ledger for cross-service visibility
    if cost_usd > 0:
        record_cost(
            db,
            user_id,
            service="flyfun-maps",
            action="chat",
            cost=cost_usd,
            metadata={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "model": model,
            },
        )

    return row.id


# --- Anonymous trial usage ---


def get_today_anon_count(db: Session, anon_id: str) -> int:
    """Count anonymous chat messages sent today."""
    return (
        db.query(func.count())
        .select_from(AnonChatUsageRow)
        .filter(
            AnonChatUsageRow.anon_id == anon_id,
            AnonChatUsageRow.timestamp >= _today_start(),
        )
        .scalar()
    ) or 0


def check_anon_rate_limit(db: Session, anon_id: str) -> None:
    """Raise 403 if anonymous daily trial limit is exceeded."""
    count = get_today_anon_count(db, anon_id)
    if count >= ANON_DAILY_LIMIT:
        raise HTTPException(
            status_code=403,
            detail="trial_exhausted",
        )


def log_anon_usage(db: Session, anon_id: str) -> None:
    """Log an anonymous chat interaction."""
    db.add(AnonChatUsageRow(anon_id=anon_id))
    db.flush()
