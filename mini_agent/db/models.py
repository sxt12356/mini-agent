from datetime import datetime, timezone
from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from mini_agent.core.config import get_settings
from mini_agent.db.session import Base


settings = get_settings()
EMBEDDING_DIM = settings.embedding_dim


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AppUser(Base):
    __tablename__ = "app_users"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(32), default="customer", nullable=False)
    disabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class Order(Base):
    __tablename__ = "orders"

    order_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    carrier: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    eta: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class RefundTicket(Base):
    __tablename__ = "refund_tickets"

    ticket_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    order_id: Mapped[str] = mapped_column(String(64), ForeignKey("orders.order_id"), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="created", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(String(256), primary_key=True)
    source: Mapped[str] = mapped_column(String(256), index=True, nullable=False)
    section: Mapped[str] = mapped_column(String(512), index=True, nullable=False)
    heading_path: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)