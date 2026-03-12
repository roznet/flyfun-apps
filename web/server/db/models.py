"""App-specific SQLAlchemy models for flyfun-apps chat usage."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

# Import Base from flyfun-common so ChatUsageRow is registered on the same
# metadata as UserRow / CostLedgerRow and created by init_shared_db().
from flyfun_common.db.models import Base  # noqa: F401 – re-export


class AnonChatUsageRow(Base):
    """Track anonymous (unauthenticated) trial chat usage."""

    __tablename__ = "anon_chat_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    anon_id: Mapped[str] = mapped_column(String(64), index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class ChatUsageRow(Base):
    __tablename__ = "chat_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    thread_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    persona_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
