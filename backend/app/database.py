import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")
_configured_data_dir = Path(os.getenv("DATA_DIR", str(PROJECT_ROOT / "data")))
DATA_DIR = (_configured_data_dir if _configured_data_dir.is_absolute() else PROJECT_ROOT / _configured_data_dir).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'niam.db'}")
if DATABASE_URL.startswith("sqlite:///") and not DATABASE_URL.startswith("sqlite:////"):
    sqlite_path = Path(DATABASE_URL.removeprefix("sqlite:///"))
    if not sqlite_path.is_absolute():
        DATABASE_URL = f"sqlite:///{(PROJECT_ROOT / sqlite_path).resolve().as_posix()}"
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
