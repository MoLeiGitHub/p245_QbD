from __future__ import annotations

import io

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user, get_study_or_404
from ..models import (
    AnalysisJob,
    AnalysisStatus,
    ControlStrategy,
    Project,
    Report,
    ReportStatus,
    Result,
    RiskAssessment,
    Run,
    Study,
    StudyDesignType,
    User,
)
from ..rbac import Permission, require_permission
from ..schemas import (
    AnalysisRunOut,
    AnalysisSummaryOut,
    ControlStrategyOut,
    DesignSpaceRequest,
    DoeGenerateRequest,
    ResultsImportOut,
    RiskUpdateOut,
    RiskUpdateRequest,
    RunOut,
    StudyCreate,
    StudyOut,
)
from ..services.analysis import run_analysis
from ..services.audit import log_action
from ..services.control import generate_control_strategy
from ..services.design_space import generate_design_space
from ..services.doe import generate_runs
from ..services.risk import update_risk_matrix

router = APIRouter(prefix='/studies', tags=['studies'])


@router.get('', response_model=list[StudyOut])
def list_studies(project_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_permission(db, user.id, project_id, Permission.REPORT_READ)
    return db.query(Study).filter(Study.project_id == project_id).order_by(Study.id.desc()).all()


@router.post('', response_model=StudyOut)
def create_study(payload: StudyCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    project = db.query(Project).filter(Project.id == payload.project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Project not found')
    require_permission(db, user.id, payload.project_id, Permission.STUDY_EDIT)
    if payload.design_type == StudyDesignType.MIXTURE_2COMP and len(payload.factors) != 2:
        raise HTTPException(status_code=400, detail='Mixture 2-component design requires exactly 2 factors')
    if payload.design_type in (StudyDesignType.FULL_FACTORIAL, StudyDesignType.FRACTIONAL_FACTORIAL) and len(payload.factors) < 2:
        raise HTTPException(status_code=400, detail='Factorial designs require at least 2 factors')

    study = Study(
        project_id=payload.project_id,
        name=payload.name,
        design_type=payload.design_type,
        factors=[f.model_dump() for f in payload.factors],
        responses=[r.model_dump() for r in payload.responses],
        created_by=user.id,
    )
    db.add(study)
    db.flush()

    report = Report(study_id=study.id, version=1, status=ReportStatus.DRAFT, created_by=user.id)
    db.add(report)

    log_action(
        db,
        project_id=study.project_id,
        actor_id=user.id,
        action='study.create',
        resource_type='study',
        resource_id=str(study.id),
        after={'name': study.name, 'design_type': study.design_type.value},
    )
    db.commit()
    db.refresh(study)
    return study


@router.post('/{study_id}/doe/generate', response_model=list[RunOut])
def generate_doe(
    study_id: int,
    payload: DoeGenerateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    study = get_study_or_404(study_id, db)
    require_permission(db, user.id, study.project_id, Permission.STUDY_EDIT)

    # Regenerate runs from scratch. Use explicit id list to avoid SQLAlchemy 2
    # IN-clause coercion issues that can surface as 500 errors.
    existing_run_ids = [r.id for r in study.runs]
    if existing_run_ids:
        db.query(Result).filter(Result.run_id.in_(existing_run_ids)).delete(synchronize_session=False)
    db.query(Run).filter(Run.study_id == study.id).delete(synchronize_session=False)

    try:
        runs = generate_runs(study, center_points=payload.center_points, fraction_p=payload.fraction_p)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    run_models: list[Run] = []
    for idx, run in enumerate(runs, start=1):
        model = Run(study_id=study.id, run_order=idx, factor_values=run)
        db.add(model)
        run_models.append(model)

    log_action(
        db,
        project_id=study.project_id,
        actor_id=user.id,
        action='study.doe.generate',
        resource_type='study',
        resource_id=str(study.id),
        after={'runs': len(runs)},
    )
    db.commit()
    for m in run_models:
        db.refresh(m)
    return run_models


@router.post('/{study_id}/results/import', response_model=ResultsImportOut)
def import_results(
    study_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    study = get_study_or_404(study_id, db)
    require_permission(db, user.id, study.project_id, Permission.STUDY_EDIT)

    content = file.file.read()
    if not content:
        raise HTTPException(status_code=400, detail='Empty CSV file')

    try:
        df = pd.read_csv(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f'Invalid CSV format: {exc}') from exc

    expected_responses = [r['name'] for r in study.responses]
    missing_value_errors: list[dict] = []
    threshold_flags: list[dict] = []

    runs_by_id = {run.id: run for run in study.runs}
    runs_by_order = {run.run_order: run for run in study.runs}

    imported = 0
    for _, row in df.iterrows():
        run = None
        if 'run_id' in row and pd.notna(row['run_id']):
            run = runs_by_id.get(int(row['run_id']))
        elif 'run_order' in row and pd.notna(row['run_order']):
            run = runs_by_order.get(int(row['run_order']))

        if not run:
            continue

        values = {}
        flags = []
        for spec in study.responses:
            name = spec['name']
            val = row.get(name)
            if pd.isna(val):
                missing_value_errors.append({'run_id': run.id, 'response': name})
                continue

            val_f = float(val)
            values[name] = val_f
            lb = spec.get('lower_bound')
            ub = spec.get('upper_bound')
            if lb is not None and val_f < float(lb):
                flag = {'run_id': run.id, 'response': name, 'type': 'below_lower_bound', 'value': val_f, 'bound': lb}
                threshold_flags.append(flag)
                flags.append(flag)
            if ub is not None and val_f > float(ub):
                flag = {'run_id': run.id, 'response': name, 'type': 'above_upper_bound', 'value': val_f, 'bound': ub}
                threshold_flags.append(flag)
                flags.append(flag)

        result = db.query(Result).filter(Result.run_id == run.id).first()
        if result:
            result.response_values = values
            result.flags = flags
        else:
            db.add(Result(run_id=run.id, response_values=values, flags=flags))
        imported += 1

    log_action(
        db,
        project_id=study.project_id,
        actor_id=user.id,
        action='study.results.import',
        resource_type='study',
        resource_id=str(study.id),
        after={'imported_runs': imported, 'flags': len(threshold_flags)},
    )
    db.commit()

    return ResultsImportOut(
        imported_runs=imported,
        missing_value_errors=missing_value_errors,
        threshold_flags=threshold_flags,
    )


@router.post('/{study_id}/analysis/run', response_model=AnalysisRunOut)
def run_study_analysis(study_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    study = get_study_or_404(study_id, db)
    require_permission(db, user.id, study.project_id, Permission.STUDY_RUN_ANALYSIS)

    job = AnalysisJob(study_id=study.id, created_by=user.id, status=AnalysisStatus.PENDING, summary={})
    db.add(job)
    db.flush()

    try:
        summary = run_analysis(study)
        job.summary = summary
        job.status = AnalysisStatus.DONE
    except Exception as exc:  # noqa: BLE001
        job.status = AnalysisStatus.FAILED
        job.error_message = str(exc)

    log_action(
        db,
        project_id=study.project_id,
        actor_id=user.id,
        action='study.analysis.run',
        resource_type='analysis_job',
        resource_id=str(job.id),
        after={'status': job.status.value},
    )
    db.commit()
    db.refresh(job)

    return AnalysisRunOut(analysis_job_id=job.id, status=job.status, error_message=job.error_message)


@router.get('/{study_id}/analysis/summary', response_model=AnalysisSummaryOut)
def get_analysis_summary(study_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    study = get_study_or_404(study_id, db)
    require_permission(db, user.id, study.project_id, Permission.REPORT_READ)

    job = (
        db.query(AnalysisJob)
        .filter(AnalysisJob.study_id == study.id)
        .order_by(AnalysisJob.created_at.desc(), AnalysisJob.id.desc())
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail='No analysis found')
    return job


@router.get('/{study_id}/dataset')
def get_study_dataset(study_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    study = get_study_or_404(study_id, db)
    require_permission(db, user.id, study.project_id, Permission.REPORT_READ)
    rows: list[dict] = []
    for run in study.runs:
        if not run.result:
            continue
        row = {'run_id': run.id, 'run_order': run.run_order}
        row.update(run.factor_values)
        row.update(run.result.response_values)
        rows.append(row)
    return {'rows': rows}


@router.post('/{study_id}/design-space/generate')
def run_design_space(
    study_id: int,
    payload: DesignSpaceRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    study = get_study_or_404(study_id, db)
    require_permission(db, user.id, study.project_id, Permission.STUDY_RUN_ANALYSIS)

    job = (
        db.query(AnalysisJob)
        .filter(AnalysisJob.study_id == study.id, AnalysisJob.status == AnalysisStatus.DONE)
        .order_by(AnalysisJob.created_at.desc(), AnalysisJob.id.desc())
        .first()
    )
    if not job:
        raise HTTPException(status_code=400, detail='Run analysis first')

    design_space = generate_design_space(
        study,
        job.summary,
        x_factor=payload.x_factor,
        y_factor=payload.y_factor,
        fixed_factors=payload.fixed_factors,
        grid_size=payload.grid_size,
    )

    updated_summary = dict(job.summary)
    updated_summary['design_space'] = design_space
    job.summary = updated_summary

    log_action(
        db,
        project_id=study.project_id,
        actor_id=user.id,
        action='study.design_space.generate',
        resource_type='analysis_job',
        resource_id=str(job.id),
        after={'feasible_ratio': design_space['feasible_ratio']},
    )
    db.commit()
    return design_space


@router.post('/{study_id}/risk/update', response_model=RiskUpdateOut)
def update_risks(
    study_id: int,
    payload: RiskUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    study = get_study_or_404(study_id, db)
    require_permission(db, user.id, study.project_id, Permission.REPORT_EDIT)

    job = (
        db.query(AnalysisJob)
        .filter(AnalysisJob.study_id == study.id, AnalysisJob.status == AnalysisStatus.DONE)
        .order_by(AnalysisJob.created_at.desc(), AnalysisJob.id.desc())
        .first()
    )
    if not job:
        raise HTTPException(status_code=400, detail='Run analysis first')

    responses = job.summary.get('responses', {})
    has_sig = any(bool(r.get('significant_terms')) for r in responses.values() if isinstance(r, dict))
    feasible_ratio = float(job.summary.get('design_space', {}).get('feasible_ratio', 0.0))

    updated, rationale = update_risk_matrix(payload.initial_matrix, feasible_ratio, has_sig)

    db.add(RiskAssessment(study_id=study.id, phase='initial', matrix=payload.initial_matrix, created_by=user.id))
    db.add(RiskAssessment(study_id=study.id, phase='updated', matrix=updated, created_by=user.id))

    log_action(
        db,
        project_id=study.project_id,
        actor_id=user.id,
        action='study.risk.update',
        resource_type='study',
        resource_id=str(study.id),
        after={'rows': len(updated)},
    )
    db.commit()

    return RiskUpdateOut(initial=payload.initial_matrix, updated=updated, rationale=rationale)


@router.post('/{study_id}/control-strategy/generate', response_model=ControlStrategyOut)
def generate_control(
    study_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    study = get_study_or_404(study_id, db)
    require_permission(db, user.id, study.project_id, Permission.REPORT_EDIT)

    job = (
        db.query(AnalysisJob)
        .filter(AnalysisJob.study_id == study.id, AnalysisJob.status == AnalysisStatus.DONE)
        .order_by(AnalysisJob.created_at.desc(), AnalysisJob.id.desc())
        .first()
    )
    if not job:
        raise HTTPException(status_code=400, detail='Run analysis first')

    design_space = job.summary.get('design_space') if isinstance(job.summary, dict) else None
    strategy = generate_control_strategy(study, job.summary, design_space)

    db.add(ControlStrategy(study_id=study.id, strategy=strategy, created_by=user.id))

    log_action(
        db,
        project_id=study.project_id,
        actor_id=user.id,
        action='study.control_strategy.generate',
        resource_type='study',
        resource_id=str(study.id),
        after={'controls': len(strategy.get('factor_controls', []))},
    )
    db.commit()
    return ControlStrategyOut(strategy=strategy)
