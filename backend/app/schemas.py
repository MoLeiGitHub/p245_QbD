from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from .models import AnalysisStatus, ProjectRole, ReportStatus, StudyDesignType


class Token(BaseModel):
    access_token: str
    token_type: str = 'bearer'


class LoginRequest(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str

    model_config = {'from_attributes': True}


class ProjectCreate(BaseModel):
    name: str
    description: str | None = None


class ProjectOut(BaseModel):
    id: int
    name: str
    description: str | None
    created_by: int
    created_at: datetime

    model_config = {'from_attributes': True}


class MembershipCreate(BaseModel):
    user_email: str
    role: ProjectRole


class MembershipOut(BaseModel):
    user_id: int
    project_id: int
    role: ProjectRole

    model_config = {'from_attributes': True}


class FactorSpec(BaseModel):
    name: str
    low: float
    high: float
    center: float | None = None


class ResponseSpec(BaseModel):
    name: str
    lower_bound: float | None = None
    upper_bound: float | None = None
    goal: str = 'target'


class StudyCreate(BaseModel):
    project_id: int
    name: str
    design_type: StudyDesignType
    factors: list[FactorSpec]
    responses: list[ResponseSpec]


class StudyOut(BaseModel):
    id: int
    project_id: int
    name: str
    design_type: StudyDesignType
    factors: list[dict]
    responses: list[dict]

    model_config = {'from_attributes': True}


class DoeGenerateRequest(BaseModel):
    center_points: int = 3
    fraction_p: int = 1


class RunOut(BaseModel):
    id: int
    run_order: int
    factor_values: dict[str, float]

    model_config = {'from_attributes': True}


class ResultsImportOut(BaseModel):
    imported_runs: int
    missing_value_errors: list[dict]
    threshold_flags: list[dict]


class AnalysisRunOut(BaseModel):
    analysis_job_id: int
    status: AnalysisStatus


class AnalysisSummaryOut(BaseModel):
    id: int
    status: AnalysisStatus
    summary: dict[str, Any]

    model_config = {'from_attributes': True}


class DesignSpaceRequest(BaseModel):
    x_factor: str
    y_factor: str
    grid_size: int = Field(default=30, ge=10, le=100)
    fixed_factors: dict[str, float] = Field(default_factory=dict)


class RiskUpdateRequest(BaseModel):
    initial_matrix: list[dict]


class RiskUpdateOut(BaseModel):
    initial: list[dict]
    updated: list[dict]
    rationale: str


class ControlStrategyOut(BaseModel):
    strategy: dict[str, Any]


class ReportOut(BaseModel):
    id: int
    study_id: int
    version: int
    status: ReportStatus
    title: str
    updated_at: datetime

    model_config = {'from_attributes': True}


class AuditLogOut(BaseModel):
    id: int
    project_id: int
    actor_id: int
    action: str
    resource_type: str
    resource_id: str
    before_json: dict | None
    after_json: dict | None
    created_at: datetime

    model_config = {'from_attributes': True}
