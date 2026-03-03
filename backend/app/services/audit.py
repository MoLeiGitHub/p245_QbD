from sqlalchemy.orm import Session

from ..models import AuditLog


def log_action(
    db: Session,
    *,
    project_id: int,
    actor_id: int,
    action: str,
    resource_type: str,
    resource_id: str,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            project_id=project_id,
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            before_json=before,
            after_json=after,
        )
    )
