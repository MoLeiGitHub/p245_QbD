from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import Base, SessionLocal, engine
from .routers import audit, auth, projects, reports, studies
from .seed import seed_users

app = FastAPI(title='QbD Beta API', version='0.1.0')

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


@app.on_event('startup')
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_users(db)
    finally:
        db.close()


@app.get('/health')
def health() -> dict:
    return {'status': 'ok'}


app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(studies.router)
app.include_router(reports.router)
app.include_router(audit.router)
