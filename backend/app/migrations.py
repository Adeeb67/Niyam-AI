from sqlalchemy import Engine

from .database import Base
from . import models  # noqa: F401


ADDITIVE_TABLES = (
    "business_profile_context",
    "analysis_findings",
    "action_metadata",
    "analysis_requests",
    "report_metadata",
    "analysis_sources",
)


def upgrade(engine: Engine) -> None:
    """Create only new additive tables; existing rows and tables are untouched."""
    Base.metadata.create_all(engine, tables=[Base.metadata.tables[name] for name in ADDITIVE_TABLES])


def downgrade(engine: Engine) -> None:
    """Drop only tables introduced by this migration; use only when their data is disposable."""
    Base.metadata.drop_all(engine, tables=[Base.metadata.tables[name] for name in reversed(ADDITIVE_TABLES)])