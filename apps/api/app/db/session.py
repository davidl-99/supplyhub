from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings


settings = get_settings()

# El engine administra la comunicación entre SQLAlchemy y PostgreSQL.
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
)

session_factory = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)