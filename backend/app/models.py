from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(20), default="user")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UserSession(Base):
    __tablename__ = "user_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Regulation(Base):
    __tablename__ = "regulations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    regulation_id: Mapped[str] = mapped_column(String(160), index=True)
    title: Mapped[str] = mapped_column(String(500))
    authority: Mapped[str] = mapped_column(String(250), default="Unknown")
    category: Mapped[str] = mapped_column(String(120), default="Regulation")
    jurisdiction: Mapped[str | None] = mapped_column(String(120), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(250), nullable=True)
    publication_date: Mapped[str | None] = mapped_column(String(40), nullable=True)
    effective_date: Mapped[str | None] = mapped_column(String(40), nullable=True)
    version_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_url: Mapped[str] = mapped_column(String(1000))
    download_url: Mapped[str] = mapped_column(String(1000))
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    file_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="DISCOVERED")
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    previous_version_id: Mapped[int | None] = mapped_column(ForeignKey("regulations.id"), nullable=True)

    previous_version = relationship("Regulation", remote_side=[id], foreign_keys=[previous_version_id])


class BusinessProfile(Base):
    __tablename__ = "business_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(250))
    industry: Mapped[str] = mapped_column(String(250))
    activities: Mapped[str] = mapped_column(Text, default="")
    state: Mapped[str] = mapped_column(String(120), default="")
    employee_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    annual_turnover: Mapped[str | None] = mapped_column(String(80), nullable=True)
    registrations: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int | None] = mapped_column(ForeignKey("business_profiles.id"), nullable=True)
    old_title: Mapped[str] = mapped_column(String(500))
    new_title: Mapped[str] = mapped_column(String(500))
    result_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    profile = relationship("BusinessProfile")


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(String(40), default="RUNNING")
    discovered: Mapped[int] = mapped_column(Integer, default=0)
    downloaded: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    updated: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    detail: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ComplianceAction(Base):
    __tablename__ = "compliance_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(30), default="Review")
    deadline: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="Pending")
    evidence: Mapped[str] = mapped_column(Text, default="")

    analysis = relationship("Analysis")


class AnalysisFinding(Base):
    __tablename__ = "analysis_findings"
    __table_args__ = (UniqueConstraint("analysis_id", "change_id", name="uq_analysis_change"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.id"), index=True)
    change_id: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(120))
    applicability: Mapped[str] = mapped_column(String(40), index=True)
    summary: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    impact: Mapped[str] = mapped_column(Text)
    conditions_json: Mapped[str] = mapped_column(Text, default="[]")
    matches_json: Mapped[str] = mapped_column(Text, default="[]")
    exemptions_json: Mapped[str] = mapped_column(Text, default="[]")
    missing_json: Mapped[str] = mapped_column(Text, default="[]")
    evidence_json: Mapped[str] = mapped_column(Text, default="[]")
    review_status: Mapped[str] = mapped_column(String(40), default="NEEDS_REVIEW")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    analysis = relationship("Analysis")


class ActionMetadata(Base):
    __tablename__ = "action_metadata"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action_id: Mapped[int] = mapped_column(ForeignKey("compliance_actions.id"), unique=True, index=True)
    profile_id: Mapped[int | None] = mapped_column(ForeignKey("business_profiles.id"), nullable=True, index=True)
    regulation_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    assigned_role: Mapped[str | None] = mapped_column(String(160), nullable=True)
    priority_rationale: Mapped[str] = mapped_column(Text, default="")
    change_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    deadline_status: Mapped[str] = mapped_column(String(40), default="UNVERIFIED")

    action = relationship("ComplianceAction")


class AnalysisRequest(Base):
    __tablename__ = "analysis_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.id"), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReportMetadata(Base):
    __tablename__ = "report_metadata"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.id"), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(30), default="READY")
    file_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AnalysisSource(Base):
    __tablename__ = "analysis_sources"
    __table_args__ = (UniqueConstraint("analysis_id", "role", name="uq_analysis_source_role"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(500))
    source_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_path: Mapped[str] = mapped_column(String(1000))


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("regulation_id", "content_hash", name="uq_regulation_hash"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    regulation_id: Mapped[str] = mapped_column(String(160), index=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    version_source_id: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BusinessProfileContext(Base):
    __tablename__ = "business_profile_context"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("business_profiles.id"), unique=True, index=True)
    jurisdictions_json: Mapped[str] = mapped_column(Text, default="[]")
    facilities_json: Mapped[str] = mapped_column(Text, default="[]")
    operational_facts_json: Mapped[str] = mapped_column(Text, default="{}")

    profile = relationship("BusinessProfile")
