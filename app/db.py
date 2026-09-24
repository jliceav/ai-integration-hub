"""Conexión a la base de datos con SQLAlchemy 2.0."""
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _make_engine(url: str):
    # SQLite necesita este flag para usarse desde varios hilos (FastAPI los usa).
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    # pool_pre_ping: si la conexión se cayó, SQLAlchemy la renueva sola (disponibilidad).
    return create_engine(url, connect_args=connect_args, pool_pre_ping=True)


engine = _make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    from app import models  # noqa: F401  (registra las tablas)

    Base.metadata.create_all(bind=engine)


def get_db() -> Iterator[Session]:
    """Dependencia de FastAPI: abre una sesión por petición y la cierra al final."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
