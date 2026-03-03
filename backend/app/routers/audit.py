from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..models import AuditLog, User
from ..rbac import Permission, require_permission
from ..schemas import AuditLogOut

router = APIRouter(tags=['audit'])


@router.get('/audit-logs', response_model=list[AuditLogOut])
def list_audit_logs(project_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_permission(db, user.id, project_id, Permission.REPORT_READ)
    return (
        db.query(AuditLog)
        .filter(AuditLog.project_id == project_id)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(500)
        .all()
    )
