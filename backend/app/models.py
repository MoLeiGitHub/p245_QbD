from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class ProjectRole(str, Enum):
    OWNER = 'owner'
    EDITOR = 'editor'
    REVIEWER = 'reviewer'
    VIEWER = 'viewer'


class StudyDesignType(str, Enum):
    FULL_FACTORIAL = 'full_factorial'
    FRACTIONAL_FACTORIAL = 'fractional_factorial'
    MIXTURE_2COMP = 'mixture_2comp'


class ReportStatus(str, Enum):
    DRAFT = 'draft'
    IN_REVIEW = 'in_review'
    APPROVED = 'approved'
    ARCHIVED = 'archived'


class AnalysisStatus(str, Enum):
    PENDING = 'pending'
    DONE = 'done'
    FAILED = 'failed'


class User(Base):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    memberships: Mapped[list[ProjectMembership]] = relationship(back_populates='user')


class Project(Base):
    __tablename__ = 'projects'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    memberships: Mapped[list[ProjectMembership]] = relationship(back_populates='project', cascade='all, delete-orphan')
    studies: Mapped[list[Study]] = relationship(back_populates='project', cascade='all, delete-orphan')


class ProjectMembership(Base):
    __tablename__ = 'project_memberships'
    __table_args__ = (UniqueConstraint('user_id', 'project_id', name='uq_project_membership'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    project_id: Mapped[int] = mapped_column(ForeignKey('projects.id', ondelete='CASCADE'))
    role: Mapped[ProjectRole] = mapped_column(SAEnum(ProjectRole), default=ProjectRole.VIEWER)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates='memberships')
    project: Mapped[Project] = relationship(back_populates='memberships')


class Study(Base):
    __tablename__ = 'studies'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey('projects.id', ondelete='CASCADE'), index=True)
    name: Mapped[str] = mapped_column(String(255))
    design_type: Mapped[StudyDesignType] = mapped_column(SAEnum(StudyDesignType))
    factors: Mapped[list[dict]] = mapped_column(JSON, default=list)
    responses: Mapped[list[dict]] = mapped_column(JSON, default=list)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped[Project] = relationship(back_populates='studies')
    runs: Mapped[list[Run]] = relationship(back_populates='study', cascade='all, delete-orphan')
    analysis_jobs: Mapped[list[AnalysisJob]] = relationship(back_populates='study', cascade='all, delete-orphan')
    reports: Mapped[list[Report]] = relationship(back_populates='study', cascade='all, delete-orphan')


class Run(Base):
    __tablename__ = 'runs'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    study_id: Mapped[int] = mapped_column(ForeignKey('studies.id', ondelete='CASCADE'), index=True)
    run_order: Mapped[int] = mapped_column(Integer)
    factor_values: Mapped[dict] = mapped_column(JSON, default=dict)

    study: Mapped[Study] = relationship(back_populates='runs')
    result: Mapped[Result | None] = relationship(back_populates='run', uselist=False, cascade='all, delete-orphan')


class Result(Base):
    __tablename__ = 'results'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey('runs.id', ondelete='CASCADE'), unique=True, index=True)
    response_values: Mapped[dict] = mapped_column(JSON, default=dict)
    flags: Mapped[list[dict]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    run: Mapped[Run] = relationship(back_populates='result')


class AnalysisJob(Base):
    __tablename__ = 'analysis_jobs'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    study_id: Mapped[int] = mapped_column(ForeignKey('studies.id', ondelete='CASCADE'), index=True)
    status: Mapped[AnalysisStatus] = mapped_column(SAEnum(AnalysisStatus), default=AnalysisStatus.PENDING)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    study: Mapped[Study] = relationship(back_populates='analysis_jobs')


class RiskAssessment(Base):
    __tablename__ = 'risk_assessments'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    study_id: Mapped[int] = mapped_column(ForeignKey('studies.id', ondelete='CASCADE'), index=True)
    phase: Mapped[str] = mapped_column(String(32))
    matrix: Mapped[list[dict]] = mapped_column(JSON, default=list)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ControlStrategy(Base):
    __tablename__ = 'control_strategies'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    study_id: Mapped[int] = mapped_column(ForeignKey('studies.id', ondelete='CASCADE'), index=True)
    strategy: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Report(Base):
    __tablename__ = 'reports'
    __table_args__ = (UniqueConstraint('study_id', 'version', name='uq_study_report_version'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    study_id: Mapped[int] = mapped_column(ForeignKey('studies.id', ondelete='CASCADE'), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[ReportStatus] = mapped_column(SAEnum(ReportStatus), default=ReportStatus.DRAFT)
    title: Mapped[str] = mapped_column(String(255), default='QbD Technical Review Report')
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    study: Mapped[Study] = relationship(back_populates='reports')


class AuditLog(Base):
    __tablename__ = 'audit_logs'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey('projects.id', ondelete='CASCADE'), index=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    action: Mapped[str] = mapped_column(String(255), index=True)
    resource_type: Mapped[str] = mapped_column(String(64))
    resource_id: Mapped[str] = mapped_column(String(64))
    before_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
