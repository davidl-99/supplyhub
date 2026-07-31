from sqlalchemy.orm import DeclarativeBase


# SQLAlchemy registra en Base.metadata todas las tablas definidas mediante estas clases.
# Alembic puede examinar esos metadatos y compararlos con PostgreSQL para detectar cambios.
# La clase DeclarativeBase es el enfoque declarativo moderno recomendado en SQLAlchemy 2.0.
class Base(DeclarativeBase):
    pass
