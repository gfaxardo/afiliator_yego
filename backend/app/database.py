from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from urllib.parse import quote_plus, urlparse, urlunparse

from app.config import settings


def _build_safe_url() -> str:
    if settings.DATABASE_URL:
        raw = settings.DATABASE_URL
    else:
        raw = (
            f"postgresql://{settings.DB_USER}:{settings.DB_PASSWORD}"
            f"@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
        )

    p = urlparse(raw)
    user = quote_plus(p.username or "", safe="") if p.username else ""
    password = quote_plus(p.password or "", safe="") if p.password else ""
    netloc = (
        f"{user}:{password}@{p.hostname}"
        + (f":{p.port}" if p.port else "")
    )
    return urlunparse((p.scheme, netloc, p.path or "", p.params, p.query, p.fragment))


engine = create_engine(
    _build_safe_url(),
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
