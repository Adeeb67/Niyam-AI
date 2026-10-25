import hashlib
from pathlib import Path
from types import SimpleNamespace

import pymupdf
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.database import Base, get_db
from backend.app.main import app
from backend.app.models import Regulation, SyncRun
from backend.app.models import ActionMetadata, Analysis, AnalysisFinding, BusinessProfile, ComplianceAction
from backend.app.services.analysis import assess_applicability, build_report, interpret_changes
from backend.app.services.compare import compare_pages, extract_pdf
from backend.app.services.impact import analyze_changes
from backend.app.services.source import SourceRecord, _check_url, discover_records
from backend.app.services.versioning import same_instrument_versions


def test_pdf_extraction_and_empty_pdf(tmp_path: Path):
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Section 4. Threshold: 25 employees.")
    pdf_path = tmp_path / "regulation.pdf"
    document.save(pdf_path)
    document.close()

    extracted = extract_pdf(str(pdf_path))
    assert extracted[0]["page"] == 1
    assert "25 employees" in extracted[0]["text"]

    empty = pymupdf.open()
    empty.new_page()
    empty_path = tmp_path / "empty.pdf"
    empty.save(empty_path)
    empty.close()
    with pytest.raises(ValueError, match="scanned PDF"):
        extract_pdf(str(empty_path))


def test_comparison_keeps_changes_and_pages():
    old = [{"page": 1, "text": "Section 4\nThe threshold is 25 employees."}, {"page": 2, "text": "File within 30 days."}]
    new = [{"page": 1, "text": "Section 4\nThe threshold is 50 employees."}, {"page": 2, "text": "File within 45 days."}]
    changes = compare_pages(old, new)
    assert len(changes) == 2
    assert changes[0]["previous_pages"] == [1]
    assert "25 employees" in changes[0]["previous_clause"]
    assert changes[0]["category"] == "Changed threshold or eligibility condition"
    assert "45 days" in changes[1]["updated_clause"]
    assert changes[1]["previous_pages"] == [2]
    assert changes[1]["category"] == "Changed deadline"
    assert changes[0]["review_status"] == "NEEDS_REVIEW"


def test_synthetic_amendment_categories_keep_sections_and_plain_summaries():
    old = [{"page": 1, "text": "Section 1\nMaintain the register annually.\n\nSection 2\nThe threshold is 100 employees.\n\nSection 3\nSubmit the return by 30 June 2026.\n\nSection 4\nRetain supporting records for 2 years.\n\nSection 5\nThe contact person shall maintain the register.\n\nSection 6\nThis rule takes effect on 1 January 2026."}]
    new = [{"page": 2, "text": "Section 1\nMaintain the register quarterly.\n\nSection 2\nThe threshold is 50 employees.\n\nSection 3\nSubmit the return by 31 May 2027.\n\nSection 4\nRetain supporting records for 5 years.\n\nSection 5\nThe contact person shall maintain the register and submit the return.\n\nSection 6\nThis rule takes effect on 1 January 2027."}]
    changes = [item for item in compare_pages(old, new) if item["category"] != "Unchanged clause"]
    assert [item["category"] for item in changes] == ["Changed reporting frequency", "Changed threshold or eligibility condition", "Changed deadline", "Changed retention period", "Changed responsible party", "Changed effective date"]
    assert all(item["section"] and item["previous_pages"] == [1] and item["updated_pages"] == [2] for item in changes)
    assert "annually to quarterly" in changes[0]["explanation"]
    assert "100 employees to 50 employees" in changes[1]["explanation"]
    assert "30 June 2026 to 31 May 2027" in changes[2]["explanation"]
    assert "2 years to 5 years" in changes[3]["explanation"]
    assert "1 January 2027" in changes[5]["explanation"]


def test_threshold_scope_uses_updated_version_and_activity_facts():
    previous = "Businesses engaged in food packaging with at least 100 employees shall submit a return."
    updated = "Businesses engaged in food packaging with 50 or more employees shall submit a return."
    change = {"id": "threshold", "category": "Changed threshold or eligibility condition", "previous_clause": previous, "updated_clause": updated, "updated_page": 1, "updated_pages": [1]}
    metadata = {"previous": {"source_id": "old"}, "updated": {"source_id": "new"}}
    pages = [{"page": 1, "text": updated}]
    profiles = [
        {"name": "A", "industry": "Food processing", "activities": "food packaging", "employee_count": 75, "registrations": ""},
        {"name": "B", "industry": "Food processing", "activities": "food packaging", "employee_count": 30, "registrations": ""},
        {"name": "C", "industry": "Food processing", "activities": "", "employee_count": 75, "registrations": ""},
    ]
    applicable, excluded, needs_verification = [analyze_changes([change], profile, metadata, [], pages)[0] for profile in profiles]
    assert applicable["applicability"] == "APPLICABLE"
    assert any("75" in item for item in applicable["matching_business_characteristics"])
    assert excluded["applicability"] == "NOT_APPLICABLE"
    assert needs_verification["applicability"] == "NEEDS_VERIFICATION"
    assert any("activities" in item.lower() for item in needs_verification["missing_information"])


def test_effective_date_is_not_a_compliance_deadline():
    text = "This rule takes effect on 1 January 2027. Submit the first return by 31 May 2027."
    change = {"id": "dates", "category": "Changed deadline", "updated_clause": text, "updated_page": 1, "updated_pages": [1]}
    finding = analyze_changes([change], {"name": "Date SME", "industry": "General", "activities": "", "employee_count": 10, "registrations": ""}, {"current": {"source_id": "v1"}}, [], [{"page": 1, "text": text}])[0]
    assert finding["effective_date"] == "2027-01-01"
    assert finding["compliance_deadline"] == "2027-05-31"
    assert finding["deadline_status"] == "VERIFIED"


def test_version_identity_accepts_strong_amendment_metadata_only():
    previous = SimpleNamespace(id=1, regulation_id="instrument-v1", content_hash="old", title="Digital Payment Rules", authority="Central Bank", jurisdiction="India", category="Rules", version_label="1.0", publication_date="2025-01-01")
    amendment = SimpleNamespace(id=2, regulation_id="instrument-v1.1", content_hash="new", title="Digital Payment Rules", authority="Central Bank", jurisdiction="India", category="Amendment", version_label="1.1", publication_date="2025-06-01")
    unrelated = SimpleNamespace(id=3, regulation_id="other", content_hash="other", title="Consumer Lending Rules", authority="Central Bank", jurisdiction="India", category="Amendment", version_label="1.1", publication_date="2025-06-01")
    assert same_instrument_versions(previous, amendment)
    assert not same_instrument_versions(previous, unrelated)


def test_applicability_does_not_assume_not_applicable():
    uncertain = assess_applicability([], {"industry": "Textiles"})
    missing = assess_applicability([], None)
    assert uncertain["outcome"] == "NEEDS_VERIFICATION"
    assert missing["outcome"] == "NEEDS_VERIFICATION"
    assert missing["missing_facts"]


def test_explicit_scope_and_exclusion_are_deterministic():
    page = [{"page": 1, "text": "This rule shall apply to companies with at least 50 employees."}]
    change = {"id": "c1", "category": "Changed threshold or eligibility condition", "previous_clause": "Applies at 25 employees.", "updated_clause": page[0]["text"], "updated_page": 1, "updated_pages": [1], "explanation": "Threshold changed", "impact": "Review staffing threshold"}
    applicable = analyze_changes([change], {"name": "A", "industry": "Manufacturing", "activities": "manufacturing", "state": "Gujarat", "employee_count": 80, "registrations": ""}, {"previous": {"source_id": "old"}, "updated": {"source_id": "new"}}, [], page)[0]
    excluded = analyze_changes([change], {"name": "B", "industry": "Manufacturing", "activities": "manufacturing", "state": "Gujarat", "employee_count": 20, "registrations": ""}, {"previous": {"source_id": "old"}, "updated": {"source_id": "new"}}, [], page)[0]
    assert applicable["applicability"] == "APPLICABLE"
    assert applicable["evidence"][0]["verified"] is True
    assert excluded["applicability"] == "NOT_APPLICABLE"
    assert excluded["exemptions"]


def test_industry_mention_alone_does_not_prove_scope():
    text = "The notification mentions manufacturing for background purposes."
    finding = analyze_changes([{"id": "industry-only", "category": "Modified obligation", "updated_clause": text, "updated_page": 1, "updated_pages": [1]}], {"name": "Factory SME", "industry": "manufacturing", "activities": "manufacturing", "state": "Gujarat", "employee_count": 12, "registrations": ""}, {"current": {"source_id": "v1"}}, [], [{"page": 1, "text": text}])[0]
    assert finding["applicability"] == "NEEDS_VERIFICATION"


def test_explicit_industry_exclusion_supports_not_applicable():
    text = "This requirement does not apply to manufacturing entities."
    finding = analyze_changes([{"id": "industry-excluded", "category": "Modified obligation", "updated_clause": text, "updated_page": 1, "updated_pages": [1]}], {"name": "Factory SME", "industry": "manufacturing", "activities": "manufacturing", "state": "Gujarat", "employee_count": 12, "registrations": ""}, {"current": {"source_id": "v1"}}, [], [{"page": 1, "text": text}])[0]
    assert finding["applicability"] == "NOT_APPLICABLE"
    assert finding["exemptions"]


def test_current_version_evidence_uses_current_source_id():
    pages = [{"page": 2, "text": "All companies shall maintain a register."}]
    changes = [{"id": "c-current", "category": "Added obligation", "previous_clause": None, "updated_clause": pages[0]["text"], "updated_page": 2, "updated_pages": [2], "explanation": "Current clause", "impact": "Assess scope"}]
    finding = analyze_changes(changes, {"name": "Test Co", "industry": "Manufacturing", "activities": "production", "state": "Gujarat", "employee_count": 20, "registrations": ""}, {"current": {"source_id": "source-current"}}, [], pages)[0]
    assert finding["evidence"][0]["document_version_id"] == "source-current"
    assert finding["evidence"][0]["source_role"] == "current"


def test_invalid_evidence_forces_verification():
    change = {"id": "c-invalid", "category": "Modified obligation", "previous_clause": None, "updated_clause": "A fabricated quote.", "updated_page": 1, "updated_pages": [1]}
    finding = analyze_changes([change], {"name": "Test Co", "industry": "Manufacturing", "employee_count": 5}, {"current": {"source_id": "v1"}}, [], [{"page": 1, "text": "Different source text."}])[0]
    assert finding["applicability"] == "NEEDS_VERIFICATION"
    assert not finding["evidence"]
    assert any("could not be verified" in item for item in finding["missing_information"])


def test_report_has_unknown_deadline_without_evidence():
    changes = [{"id": "change-1", "category": "Added obligation", "previous_clause": None, "updated_clause": "File a return", "review_status": "NEEDS_REVIEW"}]
    applicability = assess_applicability(changes, None)
    report = build_report(changes, None, applicability, "Old", "New")
    assert report["actions"][0]["deadline"] is None
    assert report["actions"][0]["verification_status"] == "Needs verification"


def test_invalid_llm_json_keeps_changes_for_review(monkeypatch):
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": "not valid json"}]}}]}

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("backend.app.services.analysis.httpx.post", lambda *args, **kwargs: Response())
    changes = [{"id": "change-1", "previous_clause": "old", "updated_clause": "new", "category": "Modified obligation", "explanation": "Text changed", "impact": "Review", "review_status": "NEEDS_REVIEW"}]
    result = interpret_changes(changes, "Old", "New", None)
    assert result[0]["interpretation_error"]
    assert result[0]["updated_clause"] == "new"


def test_source_url_allowlist():
    _check_url("https://regulatory-source-portal.vercel.app/regulations")
    with pytest.raises(ValueError, match="not approved"):
        _check_url("http://127.0.0.1/private")
    with pytest.raises(ValueError, match="not approved"):
        _check_url("https://attacker.example/file.pdf")


def test_source_discovery_uses_paginated_json(monkeypatch):
    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self.payload

    class Client:
        def __init__(self, **kwargs):
            self.offsets = []

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, url, params):
            self.offsets.append(params["offset"])
            if params["offset"] == 0:
                return Response({"data": [{"regulationId": "r1", "versionId": "v1", "title": "Notification", "sha256": "abc"}], "pagination": {"hasMore": True}})
            return Response({"data": [{"regulationId": "r2", "versionId": "v2", "title": "Guidance"}], "pagination": {"hasMore": False}})

    monkeypatch.setattr("backend.app.services.source.httpx.Client", Client)
    records = discover_records()
    assert [record.source_id for record in records] == ["v1", "v2"]
    assert records[0].download_url.endswith("/api/v1/public-documents/v1")


def test_hash_detects_content_change():
    assert hashlib.sha256(b"old").hexdigest() != hashlib.sha256(b"new").hexdigest()


def test_sync_lock_prevents_overlapping_jobs():
    from backend.app.services import jobs

    assert jobs.sync_lock.acquire(blocking=False)
    try:
        assert jobs.sync_source() == 0
    finally:
        jobs.sync_lock.release()


def _pdf_bytes(text: str) -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    content = document.tobytes()
    document.close()
    return content


def test_sync_skips_identical_hash_and_versions_changed_content(tmp_path: Path, monkeypatch):
    from backend.app.services import jobs

    test_engine = create_engine(f"sqlite:///{tmp_path / 'sync.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(test_engine)
    session_factory = sessionmaker(bind=test_engine, expire_on_commit=False)
    monkeypatch.setattr(jobs, "SessionLocal", session_factory)
    monkeypatch.setattr(jobs, "DATA_DIR", tmp_path)
    contents = [_pdf_bytes("The threshold is 25 employees."), _pdf_bytes("The threshold is 50 employees.")]
    current = {"content": contents[0], "hash": hashlib.sha256(contents[0]).hexdigest()}
    record = SourceRecord(
        source_id="version-stable", regulation_id="regulation-1", title="Threshold rule", authority="Authority",
        category="Notification", jurisdiction="India", industry="Manufacturing", publication_date=None,
        effective_date=None, version="1", source_url="https://regulatory-source-portal.vercel.app/regulations",
        download_url="https://regulatory-source-portal.vercel.app/api/v1/public-documents/version-stable",
        content_hash=current["hash"],
    )

    def fake_download(url: str, destination: Path):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(current["content"])
        return current["hash"], "application/pdf"

    monkeypatch.setattr(jobs, "discover_records", lambda source_url: [record])
    monkeypatch.setattr(jobs, "download_pdf", fake_download)
    try:
        first_id = jobs.sync_source()
        same_id = jobs.sync_source()
        assert first_id != same_id
        assert session_factory().get(SyncRun, first_id).downloaded == 1
        assert session_factory().get(SyncRun, same_id).skipped == 1

        current["content"] = contents[1]
        current["hash"] = hashlib.sha256(contents[1]).hexdigest()
        record.content_hash = current["hash"]
        changed_id = jobs.sync_source()
        db = session_factory()
        versions = db.query(Regulation).filter_by(regulation_id="regulation-1").order_by(Regulation.id).all()
        run = db.get(SyncRun, changed_id)
        assert run.downloaded == 1 and run.updated == 1
        assert len(versions) == 2
        assert versions[1].previous_version_id == versions[0].id
        assert versions[0].content_hash != versions[1].content_hash
        db.close()
    finally:
        test_engine.dispose()


def test_manual_upload_creates_report_and_pdf(tmp_path: Path, monkeypatch):
    import backend.app.main as main

    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    try:
        with TestClient(app) as client:
            registered = client.post("/api/auth/register", json={"name": "Example User", "email": "example-user@example.com", "password": "secure-test-password-123"})
            assert registered.status_code == 201
            profile = client.post("/api/business-profiles", json={"name": "Example SME", "industry": "Manufacturing", "state": "Gujarat"})
            assert profile.status_code == 201
            old_content = _pdf_bytes("Registration threshold is 25 employees.")
            new_content = _pdf_bytes("Registration threshold is 50 employees.")
            response = client.post(
                "/api/documents/upload",
                data={"profile_id": profile.json()["id"]},
                files={
                    "old_pdf": ("old.pdf", old_content, "application/pdf"),
                    "new_pdf": ("new.pdf", new_content, "application/pdf"),
                },
            )
            assert response.status_code == 200
            report = response.json()
            assert report["applicability"]["outcome"] == "NEEDS_VERIFICATION"
            assert report["changes"][0]["category"] == "Changed threshold or eligibility condition"
            assert report["findings"][0]["evidence"][0]["verified"] is True
            dashboard = client.get(f"/api/dashboard/impact?profile_id={profile.json()['id']}")
            assert dashboard.status_code == 200
            assert dashboard.json()["analysis_id"] == report["id"]
            assert "threshold" in dashboard.json()["what_changed"].lower()
            assert dashboard.json()["deadline"] is None
            assert client.get(f"/api/impact-analysis/{report['id']}").status_code == 200
            metrics = client.get("/api/dashboard/metrics").json()
            assert metrics["detected_changes"] == 1
            assert metrics["verification_needed"] == 1
            action = client.get("/api/actions").json()[0]
            assert action["profile_id"] == profile.json()["id"]
            updated = client.patch(f"/api/actions/{action['id']}", json={"status": "In progress", "assigned_role": "Compliance lead"})
            assert updated.json()["status"] == "In progress"
            assert updated.json()["assigned_role"] == "Compliance lead"
            review = client.patch(f"/api/impact-analysis/{report['id']}/findings/{report['findings'][0]['change_id']}/review", json={"status": "REVIEWED"})
            assert review.status_code == 200
            pdf_report = client.get(f"/api/reports/{report['id']}/download")
            assert pdf_report.status_code == 200
            assert pdf_report.content.startswith(b"%PDF-")
            reports = client.get("/api/reports?q=new.pdf").json()
            assert reports[0]["id"] == report["id"]
            repeated = client.post("/api/documents/upload", data={"profile_id": profile.json()["id"]}, files={"old_pdf": ("old.pdf", old_content, "application/pdf"), "new_pdf": ("new.pdf", new_content, "application/pdf")})
            assert repeated.json()["id"] == report["id"]
            assert repeated.json()["duplicate"] is True
            changed_profile = client.put(f"/api/business-profiles/{profile.json()['id']}", json={"name": "Example SME", "industry": "Manufacturing", "state": "Gujarat", "employee_count": 75})
            assert changed_profile.status_code == 200
            updated_analysis = client.post("/api/documents/upload", data={"profile_id": profile.json()["id"]}, files={"old_pdf": ("old.pdf", old_content, "application/pdf"), "new_pdf": ("new.pdf", new_content, "application/pdf")})
            assert updated_analysis.json()["id"] != report["id"]
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_current_version_analysis_does_not_claim_comparison(tmp_path: Path, monkeypatch):
    import backend.app.main as main

    test_engine = create_engine(f"sqlite:///{tmp_path / 'current.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(test_engine)
    session_factory = sessionmaker(bind=test_engine, expire_on_commit=False)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    source_path = tmp_path / "current-regulation.pdf"
    source_path.write_bytes(_pdf_bytes("All companies shall maintain a register."))
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    app.dependency_overrides[get_db] = override_get_db
    db = session_factory()
    profile = BusinessProfile(name="Current SME", industry="Manufacturing", activities="manufacturing", state="Gujarat", employee_count=12, registrations="")
    regulation = Regulation(source_id="current-v1", regulation_id="r-current", title="Current notice", authority="Authority", category="Notification", jurisdiction="India", industry="Manufacturing", publication_date="2026-01-01", effective_date="2026-02-01", version_label="1", source_url="https://example.gov.in", download_url="https://example.gov.in/current.pdf", content_hash=hashlib.sha256(source_path.read_bytes()).hexdigest(), file_path=str(source_path), status="EXTRACTED")
    db.add_all([profile, regulation])
    db.commit()
    profile_id, regulation_row_id = profile.id, regulation.id
    db.close()
    try:
        with TestClient(app) as client:
            registered = client.post("/api/auth/register", json={"name": "Example User", "email": "current-user@example.com", "password": "secure-test-password-123"})
            assert registered.status_code == 201
            response = client.post(f"/api/regulations/{regulation_row_id}/analyze", data={"profile_id": profile_id})
            assert response.status_code == 200
            report = response.json()
            assert report["is_comparison"] is False
            assert report["previous_document"] == "Historical comparison not performed"
            assert report["findings"][0]["evidence"][0]["document_version_id"] == "current-v1"
            assert report["findings"][0]["evidence"][0]["source_role"] == "current"
    finally:
        app.dependency_overrides.clear()
        test_engine.dispose()
