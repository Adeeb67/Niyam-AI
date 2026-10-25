import re
from datetime import date


def _identity(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").casefold()).strip()


def _version(value: str | None) -> tuple[int, ...] | None:
    if not value:
        return None
    numbers = re.findall(r"\d+", value)
    return tuple(int(number) for number in numbers) if numbers else None


def _date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value[:10]) if value else None
    except ValueError:
        return None


def same_instrument_versions(previous, updated) -> bool:
    if previous.id == updated.id or previous.content_hash == updated.content_hash:
        return False
    same_record = previous.regulation_id == updated.regulation_id
    if not same_record:
        if _identity(previous.title) != _identity(updated.title):
            return False
        if _identity(previous.authority) != _identity(updated.authority):
            return False
        if _identity(previous.jurisdiction) != _identity(updated.jurisdiction):
            return False
        if not any(term in _identity(updated.category) for term in ("amend", "revis", "corrigendum")):
            return False
    old_version, new_version = _version(previous.version_label), _version(updated.version_label)
    if old_version and new_version and new_version <= old_version:
        return False
    if not same_record and (not old_version or not new_version):
        return False
    old_date, new_date = _date(previous.publication_date), _date(updated.publication_date)
    if old_date and new_date and new_date < old_date:
        return False
    if not same_record and not (old_date and new_date) and not (old_version and new_version):
        return False
    return True