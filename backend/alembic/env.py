import os
import sys
from logging.config import fileConfig
from urllib.parse import quote_plus, urlparse, urlunparse

from sqlalchemy import create_engine, pool
from alembic import context

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.models.scout_liq import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
ALEMBIC_VERSION_TABLE = "alembic_version_scout_liq"


def build_safe_database_url() -> str:
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


database_url = build_safe_database_url()

config.attributes["sqlalchemy.url"] = database_url


def run_migrations_offline() -> None:
    url = config.attributes.get("sqlalchemy.url") or config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table=ALEMBIC_VERSION_TABLE,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(database_url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table=ALEMBIC_VERSION_TABLE,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
