from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from .models import ProjectMembership, ProjectRole


class Permission:
    PROJECT_MANAGE_MEMBERS = 'project.manage_members'
    STUDY_EDIT = 'study.edit'
    STUDY_RUN_ANALYSIS = 'study.run_analysis'
    REPORT_EDIT = 'report.edit'
    REPORT_SUBMIT = 'report.submit_for_review'
    REPORT_APPROVE = 'report.approve'
    REPORT_REJECT = 'report.reject'
    REPORT_READ = 'report.read'


ROLE_PERMISSIONS: dict[ProjectRole, set[str]] = {
    ProjectRole.OWNER: {
        Permission.PROJECT_MANAGE_MEMBERS,
        Permission.STUDY_EDIT,
        Permission.STUDY_RUN_ANALYSIS,
        Permission.REPORT_EDIT,
        Permission.REPORT_SUBMIT,
        Permission.REPORT_APPROVE,
        Permission.REPORT_REJECT,
        Permission.REPORT_READ,
    },
    ProjectRole.EDITOR: {
        Permission.STUDY_EDIT,
        Permission.STUDY_RUN_ANALYSIS,
        Permission.REPORT_EDIT,
        Permission.REPORT_SUBMIT,
        Permission.REPORT_READ,
    },
    ProjectRole.REVIEWER: {
        Permission.REPORT_APPROVE,
        Permission.REPORT_REJECT,
        Permission.REPORT_READ,
    },
    ProjectRole.VIEWER: {Permission.REPORT_READ},
}


def get_membership(db: Session, user_id: int, project_id: int) -> ProjectMembership:
    membership = (
        db.query(ProjectMembership)
        .filter(ProjectMembership.user_id == user_id, ProjectMembership.project_id == project_id)
        .first()
    )
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Not a project member')
    return membership


def require_permission(db: Session, user_id: int, project_id: int, permission: str) -> ProjectMembership:
    membership = get_membership(db, user_id, project_id)
    if permission not in ROLE_PERMISSIONS.get(membership.role, set()):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Permission denied')
    return membership
