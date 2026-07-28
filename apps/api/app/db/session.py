from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

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


# Cada petición recibirá su propia sesión de SQLAlchemy. Cuando la petición 
# termine, el bloque with cerrará la sesión, incluso si ocurre un error. 
# FastAPI permite usar dependencias con yield precisamente para adquirir 
# recursos antes de una petición y liberarlos después. La sesión 
# representa una unidad de trabajo temporal con PostgreSQL. No es una 
# tabla ni una conexión permanente.
def get_db_session() -> Iterator[Session]:
    with session_factory() as session:
        yield session