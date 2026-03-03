from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..models import Project, ProjectMembership, ProjectRole, User
from ..rbac import Permission, require_permission
from ..schemas import MembershipCreate, MembershipOut, ProjectCreate, ProjectOut
from ..services.audit import log_action

router = APIRouter(prefix='/projects', tags=['projects'])


@router.get('', response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    memberships = db.query(ProjectMembership).filter(ProjectMembership.user_id == user.id).all()
    project_ids = [m.project_id for m in memberships]
    if not project_ids:
        return []
    return db.query(Project).filter(Project.id.in_(project_ids)).order_by(Project.id.desc()).all()


@router.post('', response_model=ProjectOut)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    project = Project(name=payload.name, description=payload.description, created_by=user.id)
    db.add(project)
    db.flush()

    db.add(ProjectMembership(user_id=user.id, project_id=project.id, role=ProjectRole.OWNER))
    log_action(
        db,
        project_id=project.id,
        actor_id=user.id,
        action='project.create',
        resource_type='project',
        resource_id=str(project.id),
        after={'name': payload.name},
    )
    db.commit()
    db.refresh(project)
    return project


@router.post('/{project_id}/members', response_model=MembershipOut)
def add_member(
    project_id: int,
    payload: MembershipCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_permission(db, user.id, project_id, Permission.PROJECT_MANAGE_MEMBERS)

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Project not found')

    target_user = db.query(User).filter(User.email == payload.user_email, User.is_active.is_(True)).first()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Target user not found')

    membership = (
        db.query(ProjectMembership)
        .filter(ProjectMembership.user_id == target_user.id, ProjectMembership.project_id == project_id)
        .first()
    )
    before = {'role': membership.role.value} if membership else None
    if membership:
        membership.role = payload.role
    else:
        membership = ProjectMembership(user_id=target_user.id, project_id=project_id, role=payload.role)
        db.add(membership)

    log_action(
        db,
        project_id=project_id,
        actor_id=user.id,
        action='project.member.upsert',
        resource_type='project_membership',
        resource_id=f'{project_id}:{target_user.id}',
        before=before,
        after={'role': payload.role.value},
    )
    db.commit()
    db.refresh(membership)
    return membership
