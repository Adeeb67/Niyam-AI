import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import or_, select

from ..database import DATA_DIR, SessionLocal
from ..models import DocumentVersion, Regulation, SyncRun
from .compare import extract_pdf
from .source import DEFAULT_SOURCE, discover_records, download_pdf
from .versioning import same_instrument_versions


sync_lock = threading.Lock()


def sync_source(source_id: str | None = None) -> int:
    if not sync_lock.acquire(blocking=False):
        return 0
    db = SessionLocal()
    run = SyncRun(status="RUNNING")
    db.add(run)
    db.commit()
    db.refresh(run)
    try:
        records = discover_records(os.getenv("REGULATORY_SOURCE_URL", DEFAULT_SOURCE))
        if source_id:
            records = [record for record in records if record.source_id == source_id]
        run.discovered = len(records)
        for record in records:
            source_rows = db.scalars(select(Regulation).where(
                Regulation.regulation_id == record.regulation_id,
                or_(Regulation.source_id == record.source_id, Regulation.source_id.like(f"{record.source_id}|%")),
            ).order_by(Regulation.id.desc())).all()
            expected_hash = record.content_hash.lower()
            matching = next((row for row in source_rows if expected_hash and row.content_hash.lower() == expected_hash and row.status != "FAILED"), None)
            if matching:
                run.skipped += 1
                continue
            failed = next((row for row in source_rows if row.status == "FAILED"), None)
            try:
                path = DATA_DIR / "documents" / f"{record.source_id}-{expected_hash[:12] or 'latest'}.pdf"
                digest, _ = download_pdf(record.download_url, path)
                if expected_hash and digest.lower() != expected_hash:
                    raise ValueError("Downloaded PDF hash does not match source metadata")
                duplicate = db.scalar(select(Regulation).where(Regulation.regulation_id == record.regulation_id, Regulation.content_hash == digest))
                if duplicate:
                    run.skipped += 1
                    path.unlink(missing_ok=True)
                    continue
                pages = extract_pdf(str(path))
                previous = next((row for row in source_rows if row.status != "FAILED"), None)
                if previous is None:
                    previous = db.scalar(select(Regulation).where(Regulation.regulation_id == record.regulation_id, Regulation.status != "FAILED").order_by(Regulation.id.desc()))
                stored_source_id = record.source_id if not previous else f"{record.source_id}|{digest}"
                doc = failed or Regulation(
                    source_id=stored_source_id, regulation_id=record.regulation_id, title=record.title,
                    authority=record.authority, category=record.category, jurisdiction=record.jurisdiction,
                    industry=record.industry, publication_date=record.publication_date, effective_date=record.effective_date,
                    version_label=record.version, source_url=record.source_url, download_url=record.download_url,
                    content_hash=digest, file_path=str(path), status="EXTRACTED", extracted_text="\n".join(p["text"] for p in pages),
                    previous_version_id=previous.id if previous else None,
                )
                doc.source_id = stored_source_id
                db.add(doc)
                db.flush()
                db.add(DocumentVersion(regulation_id=record.regulation_id, content_hash=digest, version_source_id=record.source_id))
                existing_docs = db.scalars(select(Regulation).where(Regulation.id != doc.id, Regulation.status == "EXTRACTED")).all()
                for candidate in existing_docs:
                    if doc.previous_version_id is None and same_instrument_versions(candidate, doc):
                        doc.previous_version_id = candidate.id
                    elif candidate.previous_version_id is None and same_instrument_versions(doc, candidate):
                        candidate.previous_version_id = doc.id
                run.downloaded += 1
                if previous:
                    run.updated += 1
                db.commit()
            except Exception as exc:
                run.failed += 1
                run.detail = (run.detail + f"\n{record.title}: {str(exc)[:400]}").strip()
                db.rollback()
                failed_doc = db.scalar(select(Regulation).where(Regulation.source_id == record.source_id, Regulation.status == "FAILED"))
                if failed_doc is None:
                    failed_doc = Regulation(
                        source_id=f"{record.source_id}|failed-{run.id}", regulation_id=record.regulation_id, title=record.title,
                        authority=record.authority, category=record.category, jurisdiction=record.jurisdiction,
                        industry=record.industry, publication_date=record.publication_date, effective_date=record.effective_date,
                        version_label=record.version, source_url=record.source_url, download_url=record.download_url,
                        content_hash=record.content_hash or "unknown", status="FAILED", error=str(exc)[:1000],
                    )
                else:
                    failed_doc.status = "FAILED"
                    failed_doc.error = str(exc)[:1000]
                db.add(failed_doc)
                db.add(run)
                db.commit()
        run.status = "COMPLETED" if not run.failed else "COMPLETED_WITH_ERRORS"
    except Exception as exc:
        run.status = "FAILED"
        run.detail = str(exc)[:1000]
    finally:
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        db.close()
        sync_lock.release()
    return run.id