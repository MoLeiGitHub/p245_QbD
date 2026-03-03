from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user, get_report_or_404
from ..models import AnalysisJob, AnalysisStatus, ControlStrategy, Report, ReportStatus, RiskAssessment, User
from ..rbac import Permission, require_permission
from ..schemas import ReportOut
from ..services.audit import log_action
from ..services.reporting import build_report_payload, render_report_pdf

router = APIRouter(prefix='/reports', tags=['reports'])


@router.get('', response_model=list[ReportOut])
def list_reports(study_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    report = db.query(Report).filter(Report.study_id == study_id).first()
    if not report:
        return []
    require_permission(db, user.id, report.study.project_id, Permission.REPORT_READ)
    return db.query(Report).filter(Report.study_id == study_id).order_by(Report.version.desc()).all()


@router.post('/{report_id}/submit', response_model=ReportOut)
def submit_report(report_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    report = get_report_or_404(report_id, db)
    require_permission(db, user.id, report.study.project_id, Permission.REPORT_SUBMIT)
    if report.status != ReportStatus.DRAFT:
        raise HTTPException(status_code=409, detail='Only draft report can be submitted')

    report.status = ReportStatus.IN_REVIEW
    log_action(
        db,
        project_id=report.study.project_id,
        actor_id=user.id,
        action='report.submit',
        resource_type='report',
        resource_id=str(report.id),
        before={'status': ReportStatus.DRAFT.value},
        after={'status': ReportStatus.IN_REVIEW.value},
    )
    db.commit()
    db.refresh(report)
    return report


@router.post('/{report_id}/approve', response_model=ReportOut)
def approve_report(report_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    report = get_report_or_404(report_id, db)
    require_permission(db, user.id, report.study.project_id, Permission.REPORT_APPROVE)
    if report.status != ReportStatus.IN_REVIEW:
        raise HTTPException(status_code=409, detail='Only in-review report can be approved')

    report.status = ReportStatus.APPROVED
    log_action(
        db,
        project_id=report.study.project_id,
        actor_id=user.id,
        action='report.approve',
        resource_type='report',
        resource_id=str(report.id),
        before={'status': ReportStatus.IN_REVIEW.value},
        after={'status': ReportStatus.APPROVED.value},
    )
    db.commit()
    db.refresh(report)
    return report


@router.post('/{report_id}/reject', response_model=ReportOut)
def reject_report(report_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    report = get_report_or_404(report_id, db)
    require_permission(db, user.id, report.study.project_id, Permission.REPORT_REJECT)
    if report.status != ReportStatus.IN_REVIEW:
        raise HTTPException(status_code=409, detail='Only in-review report can be rejected')

    report.status = ReportStatus.DRAFT
    log_action(
        db,
        project_id=report.study.project_id,
        actor_id=user.id,
        action='report.reject',
        resource_type='report',
        resource_id=str(report.id),
        before={'status': ReportStatus.IN_REVIEW.value},
        after={'status': ReportStatus.DRAFT.value},
    )
    db.commit()
    db.refresh(report)
    return report


@router.get('/{report_id}/export.pdf')
def export_report(report_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    report = get_report_or_404(report_id, db)
    study = report.study
    require_permission(db, user.id, study.project_id, Permission.REPORT_READ)

    latest_analysis = (
        db.query(AnalysisJob)
        .filter(AnalysisJob.study_id == study.id, AnalysisJob.status == AnalysisStatus.DONE)
        .order_by(AnalysisJob.created_at.desc(), AnalysisJob.id.desc())
        .first()
    )
    latest_risk = (
        db.query(RiskAssessment)
        .filter(RiskAssessment.study_id == study.id, RiskAssessment.phase == 'updated')
        .order_by(RiskAssessment.created_at.desc(), RiskAssessment.id.desc())
        .first()
    )
    latest_control = (
        db.query(ControlStrategy)
        .filter(ControlStrategy.study_id == study.id)
        .order_by(ControlStrategy.created_at.desc(), ControlStrategy.id.desc())
        .first()
    )

    payload = build_report_payload(
        study,
        latest_analysis.summary if latest_analysis else None,
        latest_analysis.summary.get('design_space') if latest_analysis else None,
        {'updated': latest_risk.matrix} if latest_risk else None,
        latest_control.strategy if latest_control else None,
    )
    report.payload = payload

    pdf_bytes = render_report_pdf(report, study, payload)
    log_action(
        db,
        project_id=study.project_id,
        actor_id=user.id,
        action='report.export_pdf',
        resource_type='report',
        resource_id=str(report.id),
    )
    db.commit()

    headers = {'Content-Disposition': f'attachment; filename="qbd-report-study-{study.id}-v{report.version}.pdf"'}
    return Response(content=pdf_bytes, media_type='application/pdf', headers=headers)
