"""SQLAlchemy persistence for actions, approvals, sessions and executions."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


class MotionLifecycle(str, Enum):
    DRAFT = "draft"
    SCHEMA_VALIDATED = "schema_validated"
    STATIC_CHECKS_PASSED = "static_checks_passed"
    CLOUD_SIMULATION_PASSED = "cloud_simulation_passed"
    PLATFORM_APPROVED = "platform_approved"
    IMPORTED = "imported"
    LOCAL_SIMULATION_PASSED = "local_simulation_passed"
    HARDWARE_SMALL_AMPLITUDE_PASSED = "hardware_small_amplitude_passed"
    HARDWARE_FULL_TEMPLATE_PASSED = "hardware_full_template_passed"
    CLASSROOM_ENABLED = "classroom_enabled"
    REVOKED = "revoked"


LIFECYCLE_ORDER = tuple(MotionLifecycle)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class MotionRecord(Base):
    __tablename__ = "motions"

    id: Mapped[int] = mapped_column(primary_key=True)
    motion_id: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(120))
    lifecycle: Mapped[str] = mapped_column(String(64), default=MotionLifecycle.DRAFT.value)
    trajectory_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    package_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    design: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    cloud_report: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    local_report: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    approvals: Mapped[list["ApprovalRecord"]] = relationship(cascade="all, delete-orphan")


class ApprovalRecord(Base):
    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(primary_key=True)
    motion_id: Mapped[int] = mapped_column(ForeignKey("motions.id"), index=True)
    approval_type: Mapped[str] = mapped_column(String(64))
    approved_by: Mapped[str] = mapped_column(String(120))
    approved: Mapped[bool] = mapped_column(Boolean)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ClassroomSession(Base):
    __tablename__ = "classroom_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), unique=True)
    operator: Mapped[str] = mapped_column(String(120))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExecutionRecord(Base):
    __tablename__ = "executions"

    id: Mapped[int] = mapped_column(primary_key=True)
    execution_id: Mapped[str] = mapped_column(String(96), unique=True)
    plan_id: Mapped[str] = mapped_column(String(64), index=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    plan: Mapped[dict[str, Any]] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(32), default="submitted")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ExecutionEventRecord(Base):
    __tablename__ = "execution_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    execution_id: Mapped[str] = mapped_column(String(96), index=True)
    event_type: Mapped[str] = mapped_column(String(64))
    step_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class HardwareTestRecord(Base):
    __tablename__ = "hardware_tests"

    id: Mapped[int] = mapped_column(primary_key=True)
    motion_id: Mapped[int | None] = mapped_column(ForeignKey("motions.id"), nullable=True)
    test_type: Mapped[str] = mapped_column(String(64))
    passed: Mapped[bool] = mapped_column(Boolean)
    sanitized_summary: Mapped[dict[str, Any]] = mapped_column(JSON)
    operator: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


def create_session_factory(database_url: str):
    options = {}
    if database_url in {"sqlite://", "sqlite:///:memory:"}:
        options = {"connect_args": {"check_same_thread": False}, "poolclass": StaticPool}
    engine = create_engine(database_url, **options)
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)
