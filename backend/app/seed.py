from sqlalchemy.orm import Session

from .models import User
from .security import get_password_hash


def seed_users(db: Session) -> None:
    users = [
        ('owner@example.com', 'Owner User', 'owner123'),
        ('editor@example.com', 'Editor User', 'editor123'),
        ('reviewer@example.com', 'Reviewer User', 'reviewer123'),
        ('viewer@example.com', 'Viewer User', 'viewer123'),
    ]

    for email, full_name, password in users:
        exists = db.query(User).filter(User.email == email).first()
        if not exists:
            db.add(
                User(
                    email=email,
                    full_name=full_name,
                    hashed_password=get_password_hash(password),
                    is_active=True,
                )
            )
    db.commit()
