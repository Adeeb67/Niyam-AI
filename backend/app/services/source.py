import hashlib
import os
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup


DEFAULT_SOURCE = "https://regulatory-source-portal.vercel.app/regulations"
ALLOWED_HOSTS = {"regulatory-source-portal.vercel.app", "zwfchualkxgzdgdwusni.supabase.co"}
MAX_PDF_BYTES = int(os.getenv("MAX_PDF_BYTES", str(25 * 1024 * 1024)))


@dataclass
class SourceRecord:
    source_id: str
    regulation_id: str
    title: str
    authority: str
    category: str
    jurisdiction: str | None
    industry: str | None
    publication_date: str | None
    effective_date: str | None
    version: str | None
    source_url: str
    download_url: str
    content_hash: str


def _check_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError("Source URL host is not approved")


def discover_records(source_url: str = DEFAULT_SOURCE) -> list[SourceRecord]:
    _check_url(source_url)
    base = source_url.split("/regulations")[0]
    records: list[SourceRecord] = []
    limit, offset = 100, 0
    with httpx.Client(timeout=20, follow_redirects=False, headers={"User-Agent": "NiamAI/1.0 (public regulatory index)"}) as client:
        while True:
            response = client.get(f"{base}/api/v1/public-regulations", params={"limit": limit, "offset": offset})
            response.raise_for_status()
            payload = response.json()
            page = payload.get("data", [])
            for item in page:
                version_id = str(item.get("versionId") or item.get("id") or "")
                regulation_id = str(item.get("regulationId") or version_id)
                if not version_id or not item.get("title"):
                    continue
                download_url = f"{base}/api/v1/public-documents/{version_id}"
                records.append(SourceRecord(
                    source_id=version_id,
                    regulation_id=regulation_id,
                    title=str(item["title"]),
                    authority=str(item.get("issuingAuthority") or "Unknown"),
                    category=str(item.get("documentType") or "Regulation"),
                    jurisdiction=item.get("jurisdiction"),
                    industry=item.get("industry"),
                    publication_date=item.get("publicationDate"),
                    effective_date=item.get("effectiveDate"),
                    version=item.get("version"),
                    source_url=source_url,
                    download_url=download_url,
                    content_hash=str(item.get("sha256") or ""),
                ))
            pagination = payload.get("pagination", {})
            offset += len(page)
            if not page or not pagination.get("hasMore", False):
                break
    return records


def download_pdf(url: str, destination: Path) -> tuple[str, str]:
    _check_url(url)
    destination.parent.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with httpx.Client(timeout=httpx.Timeout(30, connect=10), follow_redirects=False) as client:
                current_url = url
                for redirect_count in range(6):
                    with client.stream("GET", current_url, headers={"User-Agent": "NiamAI/1.0"}) as response:
                        if response.is_redirect:
                            location = response.headers.get("location")
                            if not location:
                                raise ValueError("Source redirect did not include a destination")
                            current_url = str(response.url.join(location))
                            _check_url(current_url)
                            if redirect_count == 5:
                                raise ValueError("Source exceeded the redirect limit")
                            continue
                        response.raise_for_status()
                        content_type = response.headers.get("content-type", "").lower()
                        chunks = []
                        size = 0
                        for chunk in response.iter_bytes():
                            size += len(chunk)
                            if size > MAX_PDF_BYTES:
                                raise ValueError("PDF exceeds configured size limit")
                            chunks.append(chunk)
                        content = b"".join(chunks)
                        if not content.startswith(b"%PDF-"):
                            raise ValueError(f"Download is not a PDF (content-type: {content_type or 'unknown'})")
                        digest = hashlib.sha256(content).hexdigest()
                        destination.write_bytes(content)
                        return digest, content_type
        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(0.5 * (2 ** attempt))
    if last_error:
        raise last_error
    raise RuntimeError("PDF download failed")


def records_from_html(html: str, base_url: str) -> list[dict[str, str]]:
    """Fallback for source portals without a JSON listing API."""
    soup = BeautifulSoup(html, "html.parser")
    found = []
    for link in soup.select('a[href*=".pdf"]'):
        href = link.get("href", "")
        found.append({"title": link.get_text(" ", strip=True), "download_url": httpx.URL(base_url).join(href).__str__()})
    return found