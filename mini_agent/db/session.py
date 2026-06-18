from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from mini_agent.core.config import get_settings


settings = get_settings()


class Base(DeclarativeBase):
    pass


engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


@contextmanager
def db_session() -> Iterator[Session]:
    session = SessionLocal()

    try:
        yield session
        session.commit()

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()
