import json
import hashlib
import os
import secrets
import threading
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, time, timezone
from pathlib import Path

import pymupdf as fitz
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi import Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import simpleSplit
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .database import Base, DATA_DIR, SessionLocal, engine, get_db
from .models import ActionMetadata, Analysis, AnalysisFinding, AnalysisRequest, AnalysisSource, BusinessProfile, BusinessProfileContext, ComplianceAction, Regulation, ReportMetadata, SyncRun, User, UserSession
from .schemas import ActionUpdateIn, FindingReviewIn, ProfileIn, SyncSettingsIn, RegisterIn, LoginIn, BootstrapIn
from .auth import admin_user, bootstrap_admin, current_user, end_session, hash_password, verify_password, public_user, start_session
from .services.analysis import assess_applicability, build_report, interpret_changes
from .services.compare import clauses, compare_pages, extract_pdf
from .services.jobs import sync_lock, sync_source
from .services.impact import analyze_changes, applicability_summary, json_list
from .services.versioning import same_instrument_versions


Base.metadata.create_all(bind=engine)
scheduler = BackgroundScheduler(daemon=True)
sync_settings = {"enabled": os.getenv("SYNC_ENABLED", "true").lower() == "true", "interval_minutes": max(1, int(os.getenv("SYNC_INTERVAL_MINUTES", "5")))}


def schedule_sync():
    if sync_settings["enabled"]:
        scheduler.add_job(sync_source, "interval", minutes=sync_settings["interval_minutes"], id="source-sync", replace_existing=True, max_instances=1)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if sync_settings["enabled"]:
        schedule_sync()
        scheduler.start()
    yield
    if scheduler.running:
        scheduler.shutdown(wait=False)


app = FastAPI(title="Niyam AI Regulatory Intelligence API", version="1.0.0", lifespan=lifespan)
allowed_origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if origin.strip()]
app.add_middleware(CORSMiddleware, allow_origins=allowed_origins, allow_credentials=True, allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["*"])


@app.post("/api/auth/register", status_code=201)
def register(payload: RegisterIn, response: Response, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.email == payload.email)):
        raise HTTPException(409, "An account with this email already exists")
    if len(payload.password) < 10:
        raise HTTPException(422, "Password must be at least 10 characters")
    user = User(name=payload.name, email=payload.email, password_hash=hash_password(payload.password), role="user")
    db.add(user)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(409, "An account with this email already exists") from exc
    db.refresh(user)
    start_session(user, response, db)
    return public_user(user)


@app.post("/api/auth/login")
def login(payload: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")
    start_session(user, response, db)
    return public_user(user)


@app.get("/api/auth/me")
def whoami(user: User = Depends(current_user)):
    return public_user(user)


@app.post("/api/auth/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    end_session(request, response, db)


@app.get("/api/admin/users")
def admin_users(limit: int = 50, offset: int = 0, db: Session = Depends(get_db), _: User = Depends(admin_user)):
    if not 1 <= limit <= 100 or offset < 0:
        raise HTTPException(422, "limit must be 1–100 and offset must be non-negative")
    total = int(db.scalar(select(func.count(User.id))) or 0)
    users = db.scalars(select(User).order_by(User.created_at.desc(), User.id.desc()).offset(offset).limit(limit)).all()
    return {"total": total, "users": [public_user(user) for user in users], "limit": limit, "offset": offset}


@app.post("/api/admin/bootstrap")
def admin_bootstrap(payload: BootstrapIn, db: Session = Depends(get_db)):
    configured_secret = os.getenv("ADMIN_BOOTSTRAP_SECRET", "")
    if not configured_secret or not secrets.compare_digest(payload.secret, configured_secret):
        raise HTTPException(403, "Invalid bootstrap secret")
    try:
        return public_user(bootstrap_admin(os.getenv("ADMIN_BOOTSTRAP_EMAIL", ""), db))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


def as_profile(profile: BusinessProfile | None, db: Session | None = None) -> dict | None:
    if not profile:
        return None
    result = {key: getattr(profile, key) for key in ("id", "name", "industry", "activities", "state", "employee_count", "annual_turnover", "registrations")}
    context = db.scalar(select(BusinessProfileContext).where(BusinessProfileContext.profile_id == profile.id)) if db else None
    if context:
        result["jurisdictions"] = json.loads(context.jurisdictions_json)
        result["facilities"] = json.loads(context.facilities_json)
        result["operational_facts"] = json.loads(context.operational_facts_json)
    return result


def as_regulation(doc: Regulation) -> dict:
    result = {key: getattr(doc, key) for key in ("id", "regulation_id", "title", "authority", "category", "jurisdiction", "industry", "publication_date", "effective_date", "version_label", "source_url", "download_url", "content_hash", "status", "error", "retrieved_at", "previous_version_id")}
    result["source_id"] = doc.source_id.split("|", 1)[0]
    return result


def _write_upload(upload: UploadFile) -> tuple[Path, str]:
    suffix = Path(upload.filename or "document.pdf").suffix.lower()
    if suffix != ".pdf" or upload.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(415, "Upload a PDF file")
    content = upload.file.read(25 * 1024 * 1024 + 1)
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(413, "PDF exceeds the 25 MB upload limit")
    if not content.startswith(b"%PDF-"):
        raise HTTPException(400, "File signature is not a valid PDF")
    path = DATA_DIR / "uploads" / f"{uuid.uuid4().hex}.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    try:
        extract_pdf(str(path))
    except (fitz.FileDataError, ValueError) as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(422, str(exc)) from exc
    import hashlib
    return path, hashlib.sha256(content).hexdigest()


def _persist_analysis(db: Session, old_title: str, new_title: str, old_pages: list[dict], new_pages: list[dict], profile: BusinessProfile | None, source_versions: dict | None = None, *, is_comparison: bool = True, changes_override: list[dict] | None = None) -> dict:
    changes = changes_override if changes_override is not None else compare_pages(old_pages, new_pages)
    profile_data = as_profile(profile, db)
    changes = interpret_changes(changes, old_title, new_title, profile_data)
    metadata = source_versions or {}
    findings = analyze_changes([change for change in changes if change.get("category") != "Unchanged clause"], profile_data, metadata, old_pages, new_pages)
    summary = applicability_summary(findings)
    applicability = {"outcome": "NEEDS_VERIFICATION", "reason": "Per-change assessments are shown below; a regulation-level outcome is not substituted for individual clause findings.", "missing_facts": sorted({item for finding in findings for item in finding["missing_information"]})}
    report = build_report(changes, profile_data, applicability, old_title, new_title, source_versions)
    report["findings"] = findings
    report["summary"] = summary
    report["is_comparison"] = is_comparison
    report["actions"] = [{"title": finding["required_action"], "description": finding["business_impact"], "reason": finding["summary"], "change_id": finding["change_id"], "priority": finding["priority"], "deadline": finding["compliance_deadline"], "deadline_source": next((item["quoted_text"] for item in finding["evidence"] if item["source_role"] == "updated"), None) if finding["deadline_status"] == "VERIFIED" else None, "verification_status": finding["deadline_status"], "status": "Pending"} for finding in findings if finding["applicability"] != "NOT_APPLICABLE" or finding["review_required"]]
    report["executive_summary"] = _business_summary(findings, is_comparison)
    fingerprint_payload = {"profile_id": profile.id if profile else None, "profile_snapshot": profile_data, "previous": metadata.get("previous", {}).get("content_hash") or metadata.get("previous", {}).get("source_id"), "updated": metadata.get("updated", {}).get("content_hash") or metadata.get("updated", {}).get("source_id"), "current": metadata.get("current", {}).get("content_hash") or metadata.get("current", {}).get("source_id"), "comparison": is_comparison}
    fingerprint = hashlib.sha256(json.dumps(fingerprint_payload, sort_keys=True).encode()).hexdigest()
    existing_key = db.scalar(select(AnalysisRequest).where(AnalysisRequest.fingerprint == fingerprint))
    if existing_key:
        existing = db.get(Analysis, existing_key.analysis_id)
        return {"id": existing.id, **json.loads(existing.result_json), "duplicate": True}
    row = Analysis(profile_id=profile.id if profile else None, old_title=old_title, new_title=new_title, result_json=json.dumps(report, ensure_ascii=False))
    db.add(row)
    db.flush()
    db.add(AnalysisRequest(fingerprint=fingerprint, analysis_id=row.id))
    for finding in findings:
        db.add(AnalysisFinding(
            analysis_id=row.id, change_id=finding["change_id"], category=finding["category"], applicability=finding["applicability"],
            summary=finding["summary"], reason=finding["applicability_reason"], impact=finding["business_impact"],
            conditions_json=json_list(finding["applicable_conditions"]), matches_json=json_list(finding["matching_business_characteristics"]),
            exemptions_json=json_list(finding["exemptions"]), missing_json=json_list(finding["missing_information"]),
            evidence_json=json_list(finding["evidence"]), review_status="NEEDS_REVIEW" if finding["review_required"] else "PENDING_REVIEW",
        ))
    for finding in findings:
        if finding["applicability"] == "NOT_APPLICABLE" and not finding["review_required"]:
            continue
        if not finding["required_action"]:
            continue
        action = ComplianceAction(analysis_id=row.id, title=finding["required_action"][:300], description=finding["business_impact"], priority=finding["priority"], deadline=finding["compliance_deadline"], evidence=finding["summary"])
        db.add(action)
        db.flush()
        regulation_id = metadata.get("regulation_id") or metadata.get("updated", {}).get("regulation_id")
        db.add(ActionMetadata(action_id=action.id, profile_id=profile.id if profile else None, regulation_id=regulation_id, change_id=finding["change_id"], priority_rationale=finding["priority_rationale"], deadline_status=finding["deadline_status"]))
    db.add(ReportMetadata(analysis_id=row.id, status="READY"))
    for role in ("previous", "updated", "current"):
        source = metadata.get(role) or {}
        file_path = source.get("storage_path")
        if file_path and Path(file_path).is_file():
            db.add(AnalysisSource(analysis_id=row.id, role=role, title=source.get("title") or (old_title if role == "previous" else new_title), source_id=source.get("source_id"), content_hash=source.get("content_hash"), file_path=file_path))
    db.commit()
    _ensure_report_pdf(db, row.id, report)
    return {"id": row.id, **report}


def _business_summary(findings: list[dict], is_comparison: bool) -> dict:
    meaningful = [finding for finding in findings if finding["category"] != "Editorial or formatting-only change"]
    if not meaningful:
        return {"what_changed": "No material clause changes were identified." if is_comparison else "No current provisions were extracted for assessment.", "business_impact": "No business impact has been established.", "what_to_do": "No action generated.", "deadline": None, "deadline_status": "NOT_STATED", "review_note": None}
    first = meaningful[0]
    what = "; ".join(finding["summary"] for finding in meaningful[:3])
    impacts = [f"{finding['applicability']}: {finding['business_impact']}" for finding in meaningful[:3]]
    actions = [finding["required_action"] for finding in meaningful if finding["applicability"] != "NOT_APPLICABLE" or finding["review_required"]]
    verified = [finding for finding in meaningful if finding["deadline_status"] == "VERIFIED" and finding["compliance_deadline"]]
    deadline = min((finding["compliance_deadline"] for finding in verified), default=None)
    return {"what_changed": what, "business_impact": " ".join(impacts), "what_to_do": " ".join(actions[:3]) or "No action is required based on the verified exclusion.", "deadline": deadline, "deadline_status": "VERIFIED" if deadline else "UNVERIFIED", "review_note": "Deadline not verified — review the original regulation before scheduling compliance activities." if not deadline and any(f["deadline_status"] == "UNVERIFIED" for f in meaningful) else None}


def _ensure_report_pdf(db: Session, analysis_id: int, report: dict) -> Path:
    stored = db.scalar(select(ReportMetadata).where(ReportMetadata.analysis_id == analysis_id))
    if stored and stored.file_path and Path(stored.file_path).is_file():
        return Path(stored.file_path)
    destination = DATA_DIR / "reports" / f"niyam-report-{analysis_id}.pdf"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(_report_pdf_bytes(analysis_id, report))
    if not stored:
        stored = ReportMetadata(analysis_id=analysis_id)
        db.add(stored)
    stored.file_path = str(destination)
    stored.status = "READY"
    stored.generated_at = datetime.now(timezone.utc)
    db.commit()
    return destination


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "niam-ai-api"}


@app.get("/api/sources", dependencies=[Depends(current_user)])
def sources(db: Session = Depends(get_db)):
    latest = db.scalar(select(SyncRun).order_by(SyncRun.id.desc()))
    return [{"id": "regulatory-source-portal", "name": "Regulatory Source Portal", "url": os.getenv("REGULATORY_SOURCE_URL", "https://regulatory-source-portal.vercel.app/regulations"), "connectivity": "Connected" if latest and latest.status.startswith("COMPLETED") else "Not checked", "automatic_sync": sync_settings["enabled"], "interval_minutes": sync_settings["interval_minutes"], "last_sync": latest.finished_at.isoformat() if latest and latest.finished_at else None}]


@app.post("/api/sources/sync", status_code=202, dependencies=[Depends(current_user)])
def trigger_sync(background_tasks: BackgroundTasks):
    if sync_lock.locked():
        raise HTTPException(409, "A source synchronization is already running")
    background_tasks.add_task(sync_source)
    return {"status": "queued", "message": "Synchronization has been queued"}


@app.get("/api/sources/sync/status", dependencies=[Depends(current_user)])
def sync_status(db: Session = Depends(get_db)):
    latest = db.scalar(select(SyncRun).order_by(SyncRun.id.desc()))
    return {"running": sync_lock.locked(), "enabled": sync_settings["enabled"], "interval_minutes": sync_settings["interval_minutes"], "next_sync": scheduler.get_job("source-sync").next_run_time.isoformat() if scheduler.running and scheduler.get_job("source-sync") else None, "latest": {key: getattr(latest, key) for key in ("id", "status", "discovered", "downloaded", "skipped", "updated", "failed", "detail", "started_at", "finished_at")} if latest else None}


@app.put("/api/sources/sync/settings", dependencies=[Depends(current_user)])
def set_sync_settings(payload: SyncSettingsIn):
    sync_settings["enabled"] = payload.enabled
    if payload.enabled:
        schedule_sync()
        if not scheduler.running:
            scheduler.start()
    elif scheduler.running and scheduler.get_job("source-sync"):
        scheduler.remove_job("source-sync")
    return sync_settings


@app.get("/api/sources/sync/history", dependencies=[Depends(current_user)])
def sync_history(db: Session = Depends(get_db)):
    runs = db.scalars(select(SyncRun).order_by(SyncRun.id.desc()).limit(50)).all()
    return [{key: getattr(run, key) for key in ("id", "status", "discovered", "downloaded", "skipped", "updated", "failed", "detail", "started_at", "finished_at")} for run in runs]


@app.get("/api/regulations", dependencies=[Depends(current_user)])
def list_regulations(q: str = "", status: str | None = None, offset: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    limit = min(max(limit, 1), 100)
    query = select(Regulation).order_by(Regulation.retrieved_at.desc())
    if q:
        term = f"%{q[:100]}%"
        query = query.where(or_(Regulation.title.ilike(term), Regulation.authority.ilike(term), Regulation.category.ilike(term), Regulation.industry.ilike(term)))
    if status:
        query = query.where(Regulation.status == status)
    docs = db.scalars(query.offset(max(0, offset)).limit(limit)).all()
    return {"data": [as_regulation(doc) for doc in docs], "offset": offset, "limit": limit}


@app.get("/api/regulations/{regulation_id}", dependencies=[Depends(current_user)])
def regulation_detail(regulation_id: int, db: Session = Depends(get_db)):
    doc = db.get(Regulation, regulation_id)
    if not doc:
        raise HTTPException(404, "Regulation not found")
    return {**as_regulation(doc), "extracted_text": doc.extracted_text, "versions": [as_regulation(version) for version in db.scalars(select(Regulation).where(Regulation.regulation_id == doc.regulation_id).order_by(Regulation.id)).all()]}


@app.get("/api/regulations/{regulation_id}/versions", dependencies=[Depends(current_user)])
def regulation_versions(regulation_id: int, db: Session = Depends(get_db)):
    doc = db.get(Regulation, regulation_id)
    if not doc:
        raise HTTPException(404, "Regulation not found")
    return [as_regulation(version) for version in db.scalars(select(Regulation).where(Regulation.regulation_id == doc.regulation_id).order_by(Regulation.id)).all()]


@app.post("/api/regulations/{regulation_id}/retry", status_code=202, dependencies=[Depends(current_user)])
def retry_source(regulation_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    doc = db.get(Regulation, regulation_id)
    if not doc:
        raise HTTPException(404, "Regulation not found")
    if doc.status != "FAILED":
        raise HTTPException(409, "Only failed documents can be retried")
    if sync_lock.locked():
        raise HTTPException(409, "A source synchronization is already running")
    background_tasks.add_task(sync_source, doc.source_id.split("|", 1)[0])
    return {"status": "queued"}


@app.get("/api/regulations/{regulation_id}/download", dependencies=[Depends(current_user)])
def download_regulation(regulation_id: int, db: Session = Depends(get_db)):
    doc = db.get(Regulation, regulation_id)
    if not doc or not doc.file_path or not Path(doc.file_path).is_file():
        raise HTTPException(404, "Stored PDF not found")
    return StreamingResponse(open(doc.file_path, "rb"), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="regulation-{doc.id}.pdf"'})


@app.get("/api/business-profiles", dependencies=[Depends(current_user)])
def profiles(db: Session = Depends(get_db)):
    return [as_profile(profile, db) for profile in db.scalars(select(BusinessProfile).order_by(BusinessProfile.name)).all()]


@app.post("/api/business-profiles", status_code=201, dependencies=[Depends(current_user)])
def create_profile(payload: ProfileIn, db: Session = Depends(get_db)):
    data = payload.model_dump()
    jurisdictions = data.pop("jurisdictions")
    facilities = data.pop("facilities")
    operational_facts = data.pop("operational_facts")
    profile = BusinessProfile(**data)
    db.add(profile)
    db.flush()
    db.add(BusinessProfileContext(profile_id=profile.id, jurisdictions_json=json_list(jurisdictions), facilities_json=json_list(facilities), operational_facts_json=json.dumps(operational_facts)))
    db.commit()
    db.refresh(profile)
    return as_profile(profile, db)


@app.put("/api/business-profiles/{profile_id}", dependencies=[Depends(current_user)])
def update_profile(profile_id: int, payload: ProfileIn, db: Session = Depends(get_db)):
    profile = db.get(BusinessProfile, profile_id)
    if not profile:
        raise HTTPException(404, "Business profile not found")
    data = payload.model_dump()
    jurisdictions = data.pop("jurisdictions")
    facilities = data.pop("facilities")
    operational_facts = data.pop("operational_facts")
    for key, value in data.items():
        setattr(profile, key, value)
    context = db.scalar(select(BusinessProfileContext).where(BusinessProfileContext.profile_id == profile.id))
    if not context:
        context = BusinessProfileContext(profile_id=profile.id)
        db.add(context)
    context.jurisdictions_json = json_list(jurisdictions)
    context.facilities_json = json_list(facilities)
    context.operational_facts_json = json.dumps(operational_facts)
    db.commit()
    return as_profile(profile, db)


@app.delete("/api/business-profiles/{profile_id}", status_code=204, dependencies=[Depends(current_user)])
def delete_profile(profile_id: int, db: Session = Depends(get_db)):
    profile = db.get(BusinessProfile, profile_id)
    if not profile:
        raise HTTPException(404, "Business profile not found")
    db.delete(profile)
    db.commit()


@app.post("/api/documents/upload", dependencies=[Depends(current_user)])
def upload_pair(old_pdf: UploadFile = File(...), new_pdf: UploadFile = File(...), profile_id: int | None = Form(None), db: Session = Depends(get_db)):
    old_path, old_hash = _write_upload(old_pdf)
    new_path, new_hash = _write_upload(new_pdf)
    profile = db.get(BusinessProfile, profile_id) if profile_id else None
    if not profile:
        raise HTTPException(422, "Select or create an SME business profile before running impact analysis")
    old_pages, new_pages = extract_pdf(str(old_path)), extract_pdf(str(new_path))
    return _persist_analysis(db, old_pdf.filename or "Previous version", new_pdf.filename or "Updated version", old_pages, new_pages, profile, {
        "previous": {"filename": old_pdf.filename, "content_hash": old_hash, "storage_path": str(old_path)},
        "updated": {"filename": new_pdf.filename, "content_hash": new_hash, "storage_path": str(new_path)},
    })


@app.post("/api/documents/compare", dependencies=[Depends(current_user)])
def compare_existing(old_id: int = Form(...), new_id: int = Form(...), profile_id: int | None = Form(None), db: Session = Depends(get_db)):
    old_doc, new_doc = db.get(Regulation, old_id), db.get(Regulation, new_id)
    if not old_doc or not new_doc:
        raise HTTPException(404, "Both stored regulatory documents must exist")
    if not same_instrument_versions(old_doc, new_doc):
        raise HTTPException(409, "These documents cannot be verified as ordered versions of the same regulation. Check title, issuing authority, jurisdiction, amendment type, version labels, and dates.")
    if new_doc.previous_version_id not in (None, old_doc.id):
        raise HTTPException(409, "The selected documents are not a verified previous/updated version pair. Choose a linked version pair or use single-version applicability analysis.")
    profile = db.get(BusinessProfile, profile_id) if profile_id else None
    if not profile:
        raise HTTPException(422, "Select or create an SME business profile before running impact analysis")
    return _persist_analysis(db, old_doc.title, new_doc.title, extract_pdf(old_doc.file_path), extract_pdf(new_doc.file_path), profile, {
        "regulation_id": new_doc.regulation_id,
        "previous": {"source_id": as_regulation(old_doc)["source_id"], "version_id": str(old_doc.id), "regulation_id": old_doc.regulation_id, "content_hash": old_doc.content_hash, "version": old_doc.version_label, "publication_date": old_doc.publication_date, "effective_date": old_doc.effective_date, "title": old_doc.title, "storage_path": old_doc.file_path},
        "updated": {"source_id": as_regulation(new_doc)["source_id"], "version_id": str(new_doc.id), "regulation_id": new_doc.regulation_id, "content_hash": new_doc.content_hash, "version": new_doc.version_label, "publication_date": new_doc.publication_date, "effective_date": new_doc.effective_date, "title": new_doc.title, "storage_path": new_doc.file_path},
    })


@app.post("/api/regulations/{regulation_id}/analyze", dependencies=[Depends(current_user)])
def analyze_current_regulation(regulation_id: int, profile_id: int = Form(...), db: Session = Depends(get_db)):
    doc = db.get(Regulation, regulation_id)
    profile = db.get(BusinessProfile, profile_id)
    if not doc or not doc.file_path or not Path(doc.file_path).is_file():
        raise HTTPException(404, "Stored regulatory document or PDF not found")
    if not profile:
        raise HTTPException(404, "Business profile not found")
    pages = extract_pdf(doc.file_path)
    current_changes = []
    for index, clause in enumerate(clauses(pages), start=1):
        text = clause["text"]
        if not text.strip():
            continue
        current_changes.append({"id": f"current-{index}", "previous_clause": None, "updated_clause": text, "previous_page": None, "updated_page": clause["page"], "previous_pages": [], "updated_pages": [clause["page"]], "section": clause["section"], "category": "Current provision (not compared)", "explanation": "Current-version provision; no historical comparison was performed.", "impact": "Assess whether this current provision applies to the selected business profile.", "review_status": "NEEDS_REVIEW"})
    metadata = {"regulation_id": doc.regulation_id, "current": {"source_id": as_regulation(doc)["source_id"], "version_id": str(doc.id), "regulation_id": doc.regulation_id, "content_hash": doc.content_hash, "version": doc.version_label, "title": doc.title, "authority": doc.authority, "publication_date": doc.publication_date, "effective_date": doc.effective_date, "storage_path": doc.file_path}}
    return _persist_analysis(db, "Historical comparison not performed", doc.title, [], pages, profile, metadata, is_comparison=False, changes_override=current_changes)


@app.get("/api/impact-analysis", dependencies=[Depends(current_user)])
def analyses(db: Session = Depends(get_db)):
    rows = db.scalars(select(Analysis).order_by(Analysis.id.desc()).limit(100)).all()
    output = []
    for row in rows:
        data = json.loads(row.result_json)
        output.append({"id": row.id, "old_title": row.old_title, "new_title": row.new_title, "created_at": row.created_at, "profile_id": row.profile_id, "profile_name": row.profile.name if row.profile else None, "applicability": data.get("applicability"), "summary": data.get("summary", {}), "source_versions": data.get("source_versions", {}), "is_comparison": data.get("is_comparison", True), "report_status": (db.scalar(select(ReportMetadata).where(ReportMetadata.analysis_id == row.id)) or ReportMetadata(analysis_id=row.id)).status})
    return output


@app.get("/api/impact-analysis/{analysis_id}", dependencies=[Depends(current_user)])
def analysis_detail(analysis_id: int, db: Session = Depends(get_db)):
    row = db.get(Analysis, analysis_id)
    if not row:
        raise HTTPException(404, "Analysis not found")
    return {"id": row.id, "created_at": row.created_at, **json.loads(row.result_json)}


@app.get("/api/dashboard/impact", dependencies=[Depends(current_user)])
def dashboard_impact(profile_id: int, db: Session = Depends(get_db)):
    profile = db.get(BusinessProfile, profile_id)
    if not profile:
        raise HTTPException(404, "Business profile not found")
    rows = db.scalars(select(Analysis).where(Analysis.profile_id == profile_id).order_by(Analysis.id.desc()).limit(100)).all()
    for row in rows:
        report = json.loads(row.result_json)
        if not report.get("is_comparison", True):
            continue
        findings = [item for item in report.get("findings", []) if item.get("category") not in ("Unchanged clause", "Editorial or formatting-only change")]
        if not findings:
            continue
        applicable = [item for item in findings if item.get("applicability") == "APPLICABLE"]
        review = [item for item in findings if item.get("applicability") == "NEEDS_VERIFICATION"]
        selected = (applicable or review or findings)[:5]
        verified_deadline = next((item for item in findings if item.get("applicability") == "APPLICABLE" and item.get("deadline_status") == "VERIFIED" and item.get("compliance_deadline")), None)
        return {
            "profile": {"id": profile.id, "name": profile.name}, "analysis_id": row.id,
            "created_at": row.created_at.isoformat() if row.created_at else None, "source_title": row.new_title,
            "what_changed": "; ".join(dict.fromkeys(item.get("summary", "") for item in selected if item.get("summary"))) or "Review the linked findings for clause-level changes.",
            "business_impact": "; ".join(dict.fromkeys(item.get("business_impact", "") for item in selected if item.get("business_impact"))) or "Business impact requires review.",
            "required_action": "; ".join(dict.fromkeys(item.get("required_action", "") for item in selected if item.get("required_action"))) or "Review the changed clauses and document the scope decision.",
            "deadline": verified_deadline.get("compliance_deadline") if verified_deadline else None,
            "deadline_status": "VERIFIED" if verified_deadline else "NOT_VERIFIED",
            "findings": [{
                "change_id": item.get("change_id"), "category": item.get("category"), "summary": item.get("summary"),
                "applicability": item.get("applicability"), "business_impact": item.get("business_impact"),
                "required_action": item.get("required_action"), "effective_date": item.get("effective_date"),
                "compliance_deadline": item.get("compliance_deadline") if item.get("deadline_status") == "VERIFIED" else None,
                "deadline_status": item.get("deadline_status"), "priority": item.get("priority"),
                "priority_rationale": item.get("priority_rationale"), "evidence": item.get("evidence", []),
            } for item in findings[:10]],
        }
    return {
        "profile": {"id": profile.id, "name": profile.name}, "analysis_id": None, "created_at": None,
        "source_title": None, "what_changed": "No saved comparison for this business profile.",
        "business_impact": "Run a comparison to assess the changed clauses against this profile.",
        "required_action": "Select two document versions and start an analysis.", "deadline": None,
        "deadline_status": "NOT_VERIFIED", "findings": [],
    }


@app.patch("/api/impact-analysis/{analysis_id}/findings/{change_id}/review", dependencies=[Depends(current_user)])
def review_finding(analysis_id: int, change_id: str, payload: FindingReviewIn, db: Session = Depends(get_db)):
    finding = db.scalar(select(AnalysisFinding).where(AnalysisFinding.analysis_id == analysis_id, AnalysisFinding.change_id == change_id))
    if not finding:
        raise HTTPException(404, "Finding not found")
    finding.review_status = payload.status
    row = db.get(Analysis, analysis_id)
    report = json.loads(row.result_json)
    for item in report.get("findings", []):
        if item.get("change_id") == change_id:
            item["review_status"] = payload.status
            item["review_required"] = payload.status != "REVIEWED"
    row.result_json = json.dumps(report, ensure_ascii=False)
    db.commit()
    metadata = db.scalar(select(ReportMetadata).where(ReportMetadata.analysis_id == analysis_id))
    if metadata and metadata.file_path:
        Path(metadata.file_path).unlink(missing_ok=True)
    _ensure_report_pdf(db, analysis_id, report)
    return {"analysis_id": analysis_id, "change_id": change_id, "review_status": payload.status}


@app.get("/api/actions", dependencies=[Depends(current_user)])
def actions(status: str | None = None, priority: str | None = None, profile_id: int | None = None, regulation_id: str | None = None, deadline_status: str | None = None, db: Session = Depends(get_db)):
    query = select(ComplianceAction, ActionMetadata, Analysis).outerjoin(ActionMetadata, ActionMetadata.action_id == ComplianceAction.id).join(Analysis, Analysis.id == ComplianceAction.analysis_id).order_by(ComplianceAction.id.desc())
    if status:
        query = query.where(ComplianceAction.status == status)
    if priority:
        query = query.where(ComplianceAction.priority == priority)
    if profile_id:
        query = query.where(ActionMetadata.profile_id == profile_id)
    if regulation_id:
        query = query.where(ActionMetadata.regulation_id == regulation_id)
    if deadline_status:
        query = query.where(ActionMetadata.deadline_status == deadline_status)
    result = []
    for action, metadata, analysis in db.execute(query).all():
        result.append({"id": action.id, "analysis_id": action.analysis_id, "title": action.title, "description": action.description, "priority": action.priority, "deadline": action.deadline, "status": action.status, "evidence": action.evidence, "profile_id": metadata.profile_id if metadata else analysis.profile_id, "regulation_id": metadata.regulation_id if metadata else None, "change_id": metadata.change_id if metadata else None, "assigned_role": metadata.assigned_role if metadata else None, "priority_rationale": metadata.priority_rationale if metadata else "Review evidence in linked analysis.", "deadline_status": metadata.deadline_status if metadata else ("UNVERIFIED" if not action.deadline else "VERIFIED"), "updated_at": metadata.updated_at.isoformat() if metadata else None})
    return result


@app.patch("/api/actions/{action_id}", dependencies=[Depends(current_user)])
def update_action(action_id: int, payload: ActionUpdateIn, db: Session = Depends(get_db)):
    action = db.get(ComplianceAction, action_id)
    if not action:
        raise HTTPException(404, "Action not found")
    metadata = db.scalar(select(ActionMetadata).where(ActionMetadata.action_id == action.id))
    if payload.status is not None:
        action.status = payload.status
    if metadata:
        if payload.assigned_role is not None:
            metadata.assigned_role = payload.assigned_role
        metadata.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"id": action.id, "status": action.status, "assigned_role": metadata.assigned_role if metadata else None}


@app.get("/api/dashboard/metrics", dependencies=[Depends(current_user)])
def dashboard_metrics(start_date: date | None = None, end_date: date | None = None, db: Session = Depends(get_db)):
    records = int(db.scalar(select(func.count(func.distinct(Regulation.regulation_id)))) or 0)
    versions = int(db.scalar(select(func.count(Regulation.id))) or 0)
    analysis_query = select(Analysis).order_by(Analysis.id.desc())
    if start_date:
        analysis_query = analysis_query.where(Analysis.created_at >= datetime.combine(start_date, time.min, tzinfo=timezone.utc))
    if end_date:
        analysis_query = analysis_query.where(Analysis.created_at <= datetime.combine(end_date, time.max, tzinfo=timezone.utc))
    result_rows = db.scalars(analysis_query).all()
    analysis_ids = [row.id for row in result_rows]
    findings = db.scalars(select(AnalysisFinding).where(AnalysisFinding.analysis_id.in_(analysis_ids))).all() if analysis_ids else []
    comparison_ids = {row.id for row in result_rows if json.loads(row.result_json).get("is_comparison", True)}
    comparison_findings = [finding for finding in findings if finding.analysis_id in comparison_ids]
    action_query = select(ComplianceAction).where(ComplianceAction.analysis_id.in_(analysis_ids)) if analysis_ids else select(ComplianceAction).where(False)
    actions_total = db.scalars(action_query).all()
    sync_query = select(SyncRun)
    if start_date:
        sync_query = sync_query.where(SyncRun.started_at >= datetime.combine(start_date, time.min, tzinfo=timezone.utc))
    if end_date:
        sync_query = sync_query.where(SyncRun.started_at <= datetime.combine(end_date, time.max, tzinfo=timezone.utc))
    selected_runs = db.scalars(sync_query).all()
    failed_runs = sum(run.status in ("FAILED", "COMPLETED_WITH_ERRORS") for run in selected_runs)
    failed_reports = int(db.scalar(select(func.count(ReportMetadata.id)).where(ReportMetadata.status == "FAILED")) or 0)
    category_counts: dict[str, int] = {}
    monthly_changes: dict[str, int] = {}
    applicability_counts = {key: 0 for key in ("APPLICABLE", "NOT_APPLICABLE", "NEEDS_VERIFICATION")}
    for finding in comparison_findings:
        category_counts[finding.category] = category_counts.get(finding.category, 0) + 1
        applicability_counts[finding.applicability] = applicability_counts.get(finding.applicability, 0) + 1
        analysis_row = next((row for row in result_rows if row.id == finding.analysis_id), None)
        if analysis_row and analysis_row.created_at:
            month = analysis_row.created_at.strftime("%Y-%m")
            monthly_changes[month] = monthly_changes.get(month, 0) + 1
    now = datetime.now(timezone.utc).date().isoformat()
    open_actions = [action for action in actions_total if action.status != "Completed"]
    deadlines = [action for action in open_actions if action.deadline and action.deadline >= now and (db.scalar(select(ActionMetadata.deadline_status).where(ActionMetadata.action_id == action.id)) == "VERIFIED")]
    recent_analyses = sorted(result_rows, key=lambda row: row.created_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)[:10]
    return {"regulatory_records": records, "document_versions": versions, "detected_changes": len(comparison_findings), "applicable_changes": applicability_counts["APPLICABLE"], "not_applicable_changes": applicability_counts["NOT_APPLICABLE"], "verification_needed": applicability_counts["NEEDS_VERIFICATION"], "open_actions": len(open_actions), "upcoming_verified_deadlines": len(deadlines), "failed_ingestion_or_analysis_jobs": failed_runs + failed_reports, "recent_completed_analyses": len(result_rows), "changes_over_time": [{"month": key, "count": value} for key, value in sorted(monthly_changes.items())], "changes_by_category": [{"category": key, "count": value} for key, value in sorted(category_counts.items())], "changes_by_applicability": [{"applicability": key, "count": value} for key, value in applicability_counts.items()], "actions_by_priority": [{"priority": key, "count": sum(action.priority == key and action.status != "Completed" for action in actions_total)} for key in ("High", "Review", "Low")], "recent_analyses": [{"id": row.id, "old_title": row.old_title, "new_title": row.new_title, "profile_id": row.profile_id, "created_at": row.created_at.isoformat()} for row in recent_analyses]}


@app.get("/api/reports/{analysis_id}", dependencies=[Depends(current_user)])
def report_detail(analysis_id: int, db: Session = Depends(get_db)):
    return analysis_detail(analysis_id, db)


@app.get("/api/reports", dependencies=[Depends(current_user)])
def report_list(q: str = "", profile_id: int | None = None, db: Session = Depends(get_db)):
    query = select(Analysis).order_by(Analysis.id.desc()).limit(200)
    if profile_id:
        query = query.where(Analysis.profile_id == profile_id)
    rows = db.scalars(query).all()
    result = []
    for row in rows:
        report = json.loads(row.result_json)
        if q and q.casefold() not in f"{row.old_title} {row.new_title} {report.get('profile', {}).get('name', '')}".casefold():
            continue
        metadata = db.scalar(select(ReportMetadata).where(ReportMetadata.analysis_id == row.id))
        result.append({"id": row.id, "old_title": row.old_title, "new_title": row.new_title, "profile_id": row.profile_id, "profile_name": report.get("profile", {}).get("name"), "created_at": row.created_at.isoformat(), "summary": report.get("summary", {}), "source_versions": report.get("source_versions", {}), "report_status": metadata.status if metadata else "READY", "download_url": f"/api/reports/{row.id}/download"})
    return result


@app.get("/api/impact-analysis/{analysis_id}/evidence/{role}/download", dependencies=[Depends(current_user)])
def analysis_evidence_download(analysis_id: int, role: str, db: Session = Depends(get_db)):
    if role not in ("previous", "updated", "current"):
        raise HTTPException(404, "Source role not found")
    source = db.scalar(select(AnalysisSource).where(AnalysisSource.analysis_id == analysis_id, AnalysisSource.role == role))
    if not source or not Path(source.file_path).is_file():
        raise HTTPException(404, "Stored source document not found")
    return StreamingResponse(open(source.file_path, "rb"), media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{Path(source.file_path).name}"'})


def _report_pdf_bytes(analysis_id: int, report: dict) -> bytes:
    buffer = __import__("io").BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    _, height = letter
    y = height - 48
    pdf.setTitle("Niyam AI Regulatory Change Report")
    pdf.setAuthor("Niyam AI Regulatory Intelligence")
    source_versions = report.get("source_versions", {})
    def write(text: str, *, font: str = "Helvetica", size: int = 9, indent: int = 44, gap: int = 13):
        nonlocal y
        pdf.setFont(font, size)
        for line in simpleSplit(str(text), font, size, 520 - indent):
            if y < 56:
                pdf.showPage()
                y = height - 48
                pdf.setFont(font, size)
            pdf.drawString(indent, y, line)
            y -= gap

    write("NIYAM AI | REGULATORY CHANGE IMPACT REPORT", font="Helvetica-Bold", size=14, gap=22)
    write(f"Report #{analysis_id} · Generated {datetime.now(timezone.utc).isoformat()}")
    write(f"Profile: {report.get('profile', {}).get('name', 'Unknown')} · {report.get('profile', {}).get('industry', '')}")
    write(f"Previous: {report['previous_document']}", font="Helvetica-Bold")
    write(f"Updated: {report['updated_document']}", font="Helvetica-Bold")
    for role in ("previous", "updated", "current"):
        source = source_versions.get(role)
        if source:
            write(f"{role.title()} version: {source.get('version_id') or source.get('source_id') or source.get('filename')} · SHA-256 {source.get('content_hash', 'unknown')}")
            write(f"Publication date: {source.get('publication_date') or 'unknown'} · Effective date: {source.get('effective_date') or 'unknown'}")
    summary = report.get("summary", {})
    counts = summary.get("counts", {})
    write("EXECUTIVE SUMMARY", font="Helvetica-Bold", size=11, gap=18)
    write(f"Meaningful changes: {summary.get('meaningful_changes', len(report.get('findings', [])))} · Applicable: {counts.get('APPLICABLE', 0)} · Not applicable: {counts.get('NOT_APPLICABLE', 0)} · Needs verification: {counts.get('NEEDS_VERIFICATION', 0)}")
    write(f"Historical comparison performed: {'Yes' if report.get('is_comparison', True) else 'No; current-version assessment only'}")
    write("CHANGE FINDINGS", font="Helvetica-Bold", size=11, gap=18)
    findings = report.get("findings", [])
    if not findings:
        write("No clause-level findings were generated.")
    for finding in findings:
        write(f"{finding['change_id']} · {finding['category']} · {finding['applicability']} · Priority {finding['priority']}", font="Helvetica-Bold", size=10, gap=15)
        write(f"Summary: {finding['summary']}")
        write(f"Scope reasoning: {finding['applicability_reason']}")
        write(f"Conditions: {'; '.join(finding.get('applicable_conditions', [])) or 'None explicitly identified'}")
        write(f"Business matches: {'; '.join(finding.get('matching_business_characteristics', [])) or 'None verified'}")
        write(f"Exemptions: {'; '.join(finding.get('exemptions', [])) or 'None verified'}")
        write(f"Business impact: {finding['business_impact']}")
        write(f"Action: {finding['required_action']}")
        write(f"Publication: {finding.get('publication_date') or 'unknown'} · Effective: {finding.get('effective_date') or 'unknown'} · Compliance deadline: {finding.get('compliance_deadline') or 'unverified'} ({finding.get('deadline_status')})")
        write(f"Previous clause: {finding.get('previous_text') or 'No previous clause'}", indent=55)
        write(f"Updated clause: {finding.get('updated_text') or 'No updated clause'}", indent=55)
        for citation in finding.get("evidence", []):
            write(f"Evidence: {citation['document_version_id']} · p. {citation['page_number']} · {citation['source_role']} · verified={citation['verified']}")
            write(f"Quote: {citation['quoted_text']}", indent=55)
        write(f"Missing information: {'; '.join(finding.get('missing_information', [])) or 'None identified'}")
        write(f"Follow-up questions: {'; '.join(finding.get('follow_up_questions', [])) or 'None'}")
        write(f"Review status: {finding.get('review_status', 'NEEDS_REVIEW')}", gap=18)
    write("LIMITATIONS", font="Helvetica-Bold", size=11, gap=18)
    for limitation in report.get("limitations", [report.get("method", ""), report.get("disclaimer", "")]):
        write(limitation)
    write("This report is decision-support information, not legal advice. Obtain appropriate professional verification before acting.", font="Helvetica-Bold", gap=16)
    pdf.save()
    buffer.seek(0)
    return buffer.getvalue()


@app.get("/api/reports/{analysis_id}/download", dependencies=[Depends(current_user)])
def report_download(analysis_id: int, db: Session = Depends(get_db)):
    row = db.get(Analysis, analysis_id)
    if not row:
        raise HTTPException(404, "Analysis not found")
    report = json.loads(row.result_json)
    path = _ensure_report_pdf(db, analysis_id, report)
    return StreamingResponse(open(path, "rb"), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="niyam-report-{analysis_id}.pdf"'})
