import re
from difflib import SequenceMatcher

import pymupdf as fitz


SECTION = re.compile(r"(?m)^\s*((?:section|rule|regulation|clause|article)\s+[\w.-]+|\d+(?:\.\d+)*\s*[:.)-]?)\s*(.*)$", re.I)


def extract_pdf(path: str) -> list[dict]:
    pages = []
    with fitz.open(path) as pdf:
        for index, page in enumerate(pdf):
            text = page.get_text("text")
            if text.strip():
                pages.append({"page": index + 1, "text": normalize(text)})
    if not pages:
        raise ValueError("No selectable text was found. This may be a scanned PDF; OCR is not configured.")
    return pages


def normalize(text: str) -> str:
    text = text.replace("\u00ad", "")
    text = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def clauses(pages: list[dict]) -> list[dict]:
    output = []
    current_section = None
    for page in pages:
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", normalize(page["text"])) if part.strip()]
        for paragraph in paragraphs:
            lines = [line.strip() for line in paragraph.splitlines() if line.strip()]
            if not lines:
                continue
            match = SECTION.match(lines[0])
            if match:
                current_section = match.group(1).strip()
                heading_text = match.group(2).strip()
                lines = ([heading_text] if heading_text else []) + lines[1:]
            text = " ".join(lines).strip()
            if text:
                output.append({"text": text, "page": page["page"], "section": current_section})
    return output


def compare_text(old_text: str, new_text: str, old_page: int = 1, new_page: int = 1) -> list[dict]:
    old_lines = [line.strip() for line in normalize(old_text).splitlines() if line.strip()]
    new_lines = [line.strip() for line in normalize(new_text).splitlines() if line.strip()]
    return _compare_lines(old_lines, new_lines, [old_page] * len(old_lines), [new_page] * len(new_lines))


def _compare_lines(old_lines: list[str], new_lines: list[str], old_pages: list[int], new_pages: list[int]) -> list[dict]:
    matcher = SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    changes = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        old_count, new_count = i2 - i1, j2 - j1
        if tag == "replace" and old_count == new_count:
            pairs = [(tag, old_index, old_index + 1, new_index, new_index + 1) for old_index, new_index in zip(range(i1, i2), range(j1, j2))]
        else:
            pairs = [(tag, i1, i2, j1, j2)]
        for pair_tag, old_start, old_end, new_start, new_end in pairs:
            previous = "\n".join(old_lines[old_start:old_end]) or None
            updated = "\n".join(new_lines[new_start:new_end]) or None
            previous_page_refs = sorted(set(old_pages[old_start:old_end]))
            updated_page_refs = sorted(set(new_pages[new_start:new_end]))
            changes.append({
                "id": f"change-{len(changes) + 1}", "previous_clause": previous, "updated_clause": updated,
                "previous_page": previous_page_refs[0] if previous_page_refs else None,
                "updated_page": updated_page_refs[0] if updated_page_refs else None,
                "previous_pages": previous_page_refs, "updated_pages": updated_page_refs, "section": None,
                "category": classify(pair_tag, previous, updated), "explanation": "Text changed; legal significance requires review.",
                "impact": "Assess whether this provision changes a business obligation.",
                "evidence": {"old_text": previous, "new_text": updated}, "review_status": "NEEDS_REVIEW",
            })
    return changes


def compare_pages(old_pages: list[dict], new_pages: list[dict]) -> list[dict]:
    old_clauses, new_clauses = clauses(old_pages), clauses(new_pages)
    pairs, old_unmatched, new_unmatched = _match_clauses(old_clauses, new_clauses)
    changes = []
    for old_clause, new_clause in pairs:
        old_text, new_text = old_clause["text"], new_clause["text"]
        if _canonical(old_text) == _canonical(new_text):
            changes.append(_make_change("equal", old_clause, new_clause, len(changes) + 1))
            continue
        changes.append(_make_change("replace", old_clause, new_clause, len(changes) + 1))
    for clause in old_unmatched:
        changes.append(_make_change("delete", clause, None, len(changes) + 1))
    for clause in new_unmatched:
        changes.append(_make_change("insert", None, clause, len(changes) + 1))
    return changes


def _canonical(text: str) -> str:
    text = normalize(text).casefold()
    text = re.sub(r"\b(section|rule|regulation|clause|article)\s+[\w.-]+", " ", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _section_key(section: str) -> str:
    value = section.casefold().strip()
    value = re.sub(r"^(?:section|rule|regulation|clause|article)\s+", "", value)
    return re.sub(r"[^a-z0-9.]+", "", value)


def _match_clauses(old: list[dict], new: list[dict]) -> tuple[list[tuple[dict, dict]], list[dict], list[dict]]:
    pairs: list[tuple[dict, dict]] = []
    used_old: set[int] = set()
    used_new: set[int] = set()

    # Section/clause identifiers are the strongest match; retain a one-to-one mapping.
    old_by_section: dict[str, list[int]] = {}
    new_by_section: dict[str, list[int]] = {}
    for index, clause in enumerate(old):
        if clause.get("section"):
            old_by_section.setdefault(_section_key(clause["section"]), []).append(index)
    for index, clause in enumerate(new):
        if clause.get("section"):
            new_by_section.setdefault(_section_key(clause["section"]), []).append(index)
    for section, old_indexes in old_by_section.items():
        new_indexes = new_by_section.get(section, [])
        if len(old_indexes) == len(new_indexes) == 1:
            old_index, new_index = old_indexes[0], new_indexes[0]
            pairs.append((old[old_index], new[new_index]))
            used_old.add(old_index)
            used_new.add(new_index)

    # Pair remaining clauses by textual similarity for renumbered or moved clauses.
    candidates = []
    for old_index, old_clause in enumerate(old):
        if old_index in used_old:
            continue
        old_text = _canonical(old_clause["text"])
        for new_index, new_clause in enumerate(new):
            if new_index in used_new:
                continue
            new_text = _canonical(new_clause["text"])
            if not old_text or not new_text:
                continue
            score = SequenceMatcher(None, old_text, new_text, autojunk=False).ratio()
            old_words, new_words = set(old_text.split()), set(new_text.split())
            overlap = len(old_words & new_words) / max(1, len(old_words | new_words))
            if score >= 0.45 or overlap >= 0.4:
                candidates.append((max(score, overlap), old_index, new_index))
    for _, old_index, new_index in sorted(candidates, reverse=True):
        if old_index not in used_old and new_index not in used_new:
            pairs.append((old[old_index], new[new_index]))
            used_old.add(old_index)
            used_new.add(new_index)

    return pairs, [clause for index, clause in enumerate(old) if index not in used_old], [clause for index, clause in enumerate(new) if index not in used_new]


def _make_change(tag: str, old_clause: dict | None, new_clause: dict | None, index: int) -> dict:
    previous = old_clause["text"] if old_clause else None
    updated = new_clause["text"] if new_clause else None
    old_page = old_clause.get("page") if old_clause else None
    new_page = new_clause.get("page") if new_clause else None
    old_section = old_clause.get("section") if old_clause else None
    new_section = new_clause.get("section") if new_clause else None
    category = classify(tag, previous, updated)
    editorial = tag == "replace" and _canonical(previous or "") == _canonical(updated or "")
    if editorial:
        category = "Editorial or formatting-only change"
    elif tag == "equal":
        category = "Unchanged clause"
    before = previous or "(none)"
    after = updated or "(none)"
    summary = _plain_change_summary(tag, category, previous, updated)
    return {
        "id": f"change-{index}", "previous_clause": previous, "updated_clause": updated,
        "previous_page": old_page, "updated_page": new_page,
        "previous_pages": [old_page] if old_page else [], "updated_pages": [new_page] if new_page else [],
        "section": new_section or old_section, "previous_section": old_section, "updated_section": new_section,
        "category": category, "explanation": summary,
        "impact": _plain_impact(category, previous, updated),
        "evidence": {"old_text": previous, "new_text": updated},
        "review_status": "NEEDS_REVIEW" if category != "Unchanged clause" else "UNCHANGED",
    }


def _plain_impact(category: str, previous: str | None, updated: str | None) -> str:
    text = f"{previous or ''} {updated or ''}"
    if category == "Changed reporting frequency":
        return "Staff will need to update the affected register more often under the new schedule."
    if category == "Changed threshold or eligibility condition":
        return "The new cutoff may bring businesses of a different size into or out of the reporting requirement."
    if category == "Changed deadline":
        return "The first or next filing may need to be completed earlier under the updated date."
    if category == "Changed retention period":
        return "The business must keep supporting records for the updated retention period."
    if category == "Changed responsible party":
        return "The business should make sure the named contact person owns these responsibilities."
    if category == "Changed effective date":
        return "This is when the updated rule starts to apply; it is not automatically the filing deadline."
    return "Review whether the updated wording changes a business task or recordkeeping process."


def _plain_change_summary(tag: str, category: str, previous: str | None, updated: str | None) -> str:
    if tag == "insert":
        return f"A new requirement was added: {(updated or '')[:180]}"
    if tag == "delete":
        return f"This requirement was removed: {(previous or '')[:180]}"
    old, new = previous or "", updated or ""
    if category == "Changed reporting frequency":
        old_frequency = _first_match(old, r"\b(quarterly|monthly|annually|annual|yearly|semi-annually)\b")
        new_frequency = _first_match(new, r"\b(quarterly|monthly|annually|annual|yearly|semi-annually)\b")
        if old_frequency and new_frequency:
            return f"The record update schedule changes from {old_frequency} to {new_frequency}."
    if category == "Changed threshold or eligibility condition":
        threshold_pattern = r"\b(?:(?:at least|not less than|minimum of)\s+)?\d[\d,]*\s+(?:or more\s+)?(?:employees|workers|staff)\b"
        old_number = _first_match(old, threshold_pattern)
        new_number = _first_match(new, threshold_pattern)
        if old_number and new_number:
            return f"The employee reporting threshold changes from {old_number} to {new_number}."
    if category == "Changed deadline":
        old_date = _explicit_date_text(old)
        new_date = _explicit_date_text(new)
        if old_date and new_date:
            return f"The submission deadline changes from {old_date} to {new_date}."
    if category == "Changed retention period":
        old_years = _first_match(old, r"\b\d+\s+years?\b")
        new_years = _first_match(new, r"\b\d+\s+years?\b")
        if old_years and new_years:
            return f"Required record retention changes from {old_years} to {new_years}."
    if category == "Changed effective date":
        new_date = _explicit_date_text(new)
        if new_date:
            return f"The updated requirement takes effect on {new_date}."
    if category == "Changed responsible party":
        return "The updated text spells out the contact person's responsibilities more clearly."
    return f"The wording changed from: {old[:100]} Updated wording: {new[:100]}"


def _first_match(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, re.I)
    return match.group(0) if match else None


def _explicit_date_text(text: str) -> str | None:
    match = re.search(r"\b(?:\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}|(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}|\d{4}-\d{2}-\d{2})\b", text, re.I)
    return match.group(0) if match else None


def classify(tag: str, previous: str | None, updated: str | None) -> str:
    text = f"{previous or ''} {updated or ''}".lower()
    if tag == "insert":
        return "Added obligation"
    if tag == "delete":
        return "Removed obligation"
    if re.search(r"\b(deadline|within\s+\d+\s+days|before|on or before|due date|due by|submit by|submit\b.{0,60}\bby|submission by|no later than|days of)\b", text):
        return "Changed deadline"
    if re.search(r"\b(takes effect|effective from|comes into force|effective date)\b", text):
        return "Changed effective date"
    if re.search(r"\b(retain|retention|keep records?|preserve records?)\b", text) and re.search(r"\b\d+\s+years?\b", text):
        return "Changed retention period"
    if re.search(r"\b(contact person|responsible person|officer in charge|shall be responsible|must be responsible|contact person is responsible)\b", text):
        return "Changed responsible party"
    if re.search(r"\b(quarterly|annually|annual|monthly|each quarter|every quarter)\b", text):
        return "Changed reporting frequency"
    if re.search(r"\b(threshold|turnover|employee|eligibility|exempt|exemption)\b", text):
        return "Changed threshold or eligibility condition"
    if re.search(r"\b(penalty|liable|fine|imprisonment|consequence)\b", text):
        return "Changed penalty or consequence"
    if re.search(r"\b(means|definition|defined as)\b", text):
        return "Changed definition"
    if re.search(r"\b(shall|must|required to|obligation)\b", text):
        return "Modified obligation"
    return "Uncertain change"