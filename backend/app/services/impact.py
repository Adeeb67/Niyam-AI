import json
import re
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


Applicability = Literal["APPLICABLE", "NOT_APPLICABLE", "NEEDS_VERIFICATION"]
MONTHS = {name.casefold(): index for index, name in enumerate(("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"), start=1)}


class EvidenceReference(BaseModel):
    document_version_id: str
    clause_id: str | None = None
    page_number: int = Field(ge=1)
    quoted_text: str = Field(min_length=1)
    source_role: Literal["previous", "updated", "current"]
    verified: bool = False


class ChangeFinding(BaseModel):
    change_id: str
    category: str
    previous_text: str | None = None
    updated_text: str | None = None
    summary: str
    applicability: Applicability
    applicability_reason: str
    applicable_conditions: list[str] = Field(default_factory=list)
    matching_business_characteristics: list[str] = Field(default_factory=list)
    exemptions: list[str] = Field(default_factory=list)
    business_impact: str
    required_action: str
    priority: Literal["High", "Review", "Low"]
    priority_rationale: str
    publication_date: str | None = None
    effective_date: str | None = None
    compliance_deadline: str | None = None
    deadline_status: Literal["VERIFIED", "UNVERIFIED", "NOT_STATED"] = "UNVERIFIED"
    evidence: list[EvidenceReference] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)
    review_required: bool = True


def _version_id(metadata: dict, role: str) -> str:
    version = metadata.get(role) or (metadata.get("current") if role == "updated" else None) or {}
    return str(version.get("source_id") or version.get("version_id") or version.get("content_hash") or "unknown")


def validate_evidence(change: dict, old_pages: list[dict], new_pages: list[dict], metadata: dict) -> list[dict]:
    references: list[dict] = []
    for role, clause_key, pages, version_role in (
        ("previous", "previous_clause", old_pages, "previous"),
        ("updated", "updated_clause", new_pages, "updated"),
    ):
        quoted = (change.get(clause_key) or "").strip()
        if not quoted:
            continue
        target_pages = change.get(f"{role}_pages") or ([change.get(f"{role}_page")] if change.get(f"{role}_page") else [])
        matches = []
        for page in pages:
            page_number = int(page["page"])
            if target_pages and page_number not in target_pages:
                continue
            if quoted.casefold() in str(page["text"]).casefold():
                matches.append(page_number)
        for page_number in matches:
            references.append({
                "document_version_id": _version_id(metadata, version_role),
                "clause_id": change.get("section"),
                "page_number": page_number,
                "quoted_text": quoted,
                "source_role": "current" if role == "updated" and not metadata.get("previous") else role,
                "verified": True,
            })
    return references


def _explicit_dates(text: str) -> list[dict]:
    date_pattern = r"(?:\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}|(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}|\d{4}-\d{2}-\d{2})"
    results = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
        for match in re.finditer(date_pattern, sentence, re.I):
            raw = match.group(0)
            parsed = None
            for pattern in ("%d %B %Y", "%B %d, %Y", "%B %d %Y", "%Y-%m-%d"):
                try:
                    parsed = datetime.strptime(raw, pattern).date().isoformat()
                    break
                except ValueError:
                    continue
            if not parsed:
                continue
            lower = sentence.casefold()
            if re.search(r"\b(takes? effect|effective from|comes? into force|shall come into force|effective date)\b", lower):
                kind = "effective_date"
            elif re.search(r"\b(due by|deadline|submit by|submit\b.{0,60}\bby|submission by|on or before|no later than|within .* days)\b", lower):
                kind = "compliance_deadline"
            elif re.search(r"\b(published|publication date|issued on)\b", lower):
                kind = "publication_date"
            else:
                kind = "unclassified_date"
            results.append({"date": parsed, "kind": kind, "quote": sentence.strip()})
    return results


def _scope_result(change: dict, profile: dict | None, regulation: dict) -> dict:
    if not profile:
        return {"applicability": "NEEDS_VERIFICATION", "reason": "Select a business profile to assess this change.", "conditions": [], "matches": [], "exemptions": [], "missing": ["Business activities", "Operating jurisdiction", "Relevant registrations and thresholds"], "questions": ["Which activities and jurisdictions does this business operate in?"]}

    previous_text = str(change.get("previous_clause") or "").casefold()
    updated_text = str(change.get("updated_clause") or "").casefold()
    text = updated_text or previous_text
    profile_industry = str(profile.get("industry") or "").strip().casefold()
    activities = str(profile.get("activities") or "").casefold()
    registrations = str(profile.get("registrations") or "").casefold()
    state = str(profile.get("state") or "").strip().casefold()
    jurisdictions = [str(value).strip().casefold() for value in profile.get("jurisdictions", []) if str(value).strip()]
    matches: list[str] = []
    conditions: list[str] = []
    exemptions: list[str] = []
    missing: list[str] = []
    questions: list[str] = []

    industry_excluded = bool(profile_industry and re.search(rf"\b(?:does not apply to|shall not apply to|excluded from)\s+(?:the\s+)?{re.escape(profile_industry)}\b", text))
    if industry_excluded:
        exemptions.append(f"The clause explicitly excludes {profile.get('industry')}.")
        return {"applicability": "NOT_APPLICABLE", "reason": "The updated clause explicitly excludes the business's stated industry.", "conditions": [], "matches": [], "exemptions": exemptions, "missing": [], "questions": []}
    if profile_industry and profile_industry in text:
        matches.append(f"Profile industry '{profile.get('industry')}' appears in the changed clause.")
        conditions.append(f"Clause explicitly mentions {profile.get('industry')}.")
    activity_scope = bool(re.search(r"\b(?:engaged in|carrying on|conducting|operating|manufacturing|packaging|processing)\b", text))
    if activity_scope and not activities:
        missing.append("Business activities are needed to evaluate the clause's activity scope.")
        questions.append("Which activities does the business perform that are named in the changed clause?")
    elif activities:
        activity_terms = [term for term in re.findall(r"[a-z]{5,}", activities) if term not in {"business", "activity", "activities", "company", "manufacturing", "products"}]
        activity_matches = [term for term in dict.fromkeys(activity_terms) if term in text]
        if activity_matches:
            matches.append(f"Business activities match clause terms: {', '.join(activity_matches)}.")
            conditions.append(f"Clause mentions activity: {', '.join(activity_matches)}.")
    if state and state in text:
        matches.append(f"Profile operating state '{profile.get('state')}' appears in the changed clause.")
        conditions.append(f"Clause names operating jurisdiction {profile.get('state')}.")
    for jurisdiction in jurisdictions:
        if jurisdiction != state and jurisdiction in text:
            matches.append(f"Profile operating jurisdiction '{jurisdiction}' appears in the changed clause.")
            conditions.append(f"Clause names operating jurisdiction {jurisdiction}.")

    count = profile.get("employee_count")
    threshold = re.search(r"\b(?:at least|not less than|minimum of|more than|exceeding|over)\s+(\d[\d,]*)\s+(?:employees|workers|staff)\b|\b(\d[\d,]*)\s+or more\s+(?:employees|workers|staff)\b|\b(?:threshold\s+(?:is|of|set at|reduced to|increased to)?\s*)(\d[\d,]*)\s+(?:employees|workers|staff)\b|\b(?:businesses|entities|companies)\s+with\s+(\d[\d,]*)\s+(?:or more\s+)?(?:employees|workers|staff)\b", text)
    upper_bound = re.search(r"\b(?:fewer than|less than|not more than|up to|maximum of)\s+(\d[\d,]*)\s+(?:employees|workers|staff)\b|\b(\d[\d,]*)\s+or fewer\s+(?:employees|workers|staff)\b", text)
    explicit_scope = bool(re.search(r"\b(?:applies to|applicable to|shall apply to|only entities|only companies|threshold|businesses with|entities with|companies with)\b", text) or re.search(r"\b(?:businesses|entities|companies)\b.{0,80}\b(?:employees|workers|staff)\b", text))
    if threshold:
        number = int(next(group for group in threshold.groups() if group).replace(",", ""))
        comparator_text = threshold.group(0).casefold()
        inclusive = not any(w in comparator_text for w in ("more than", "exceeding", "over"))
        conditions.append(f"Employee threshold in clause: {'at least' if inclusive else 'more than'} {number}.")
        if count is None:
            missing.append("Employee count is needed to evaluate the clause threshold.")
            questions.append("How many employees does the business have under the measure stated in this regulation?")
        else:
            qualifies = count >= number if inclusive else count > number
            if qualifies:
                matches.append(f"Employee count {count} satisfies the stated threshold of {number}.")
            elif explicit_scope:
                exemptions.append(f"Employee count {count} is below the clause's explicit scope threshold of {number}.")
                return {"applicability": "NOT_APPLICABLE", "reason": "The clause explicitly limits scope by employee threshold, and the saved profile is below that threshold.", "conditions": conditions, "matches": matches, "exemptions": exemptions, "missing": [], "questions": []}
            else:
                missing.append("Confirm whether the threshold defines scope or an exemption.")
    elif upper_bound:
        number = int((upper_bound.group(1) or upper_bound.group(2)).replace(",", ""))
        conditions.append(f"Employee upper bound in clause: {number}.")
        if count is None:
            missing.append("Employee count is needed to evaluate the clause threshold.")
            questions.append("How many employees does the business have?")
        else:
            upper_text = upper_bound.group(0).casefold()
            qualifies = count <= number if "or fewer" in upper_text or any(w in upper_text for w in ("not more", "up to", "maximum")) else count < number
            if qualifies:
                matches.append(f"Employee count {count} is within the explicit upper bound of {number}.")
            elif explicit_scope:
                exemptions.append(f"Employee count {count} is outside the explicit upper bound of {number}.")
                return {"applicability": "NOT_APPLICABLE", "reason": "The clause explicitly limits scope by employee count, and the saved profile exceeds that limit.", "conditions": conditions, "matches": matches, "exemptions": exemptions, "missing": [], "questions": []}

    registration_terms = [term for term in ("gst", "factory licence", "fssai", "shops and establishments", "cin") if term in text]
    if registration_terms:
        conditions.extend(f"Clause references registration: {term}." for term in registration_terms)
        if any(term in registrations for term in registration_terms):
            matches.append("A registration named in the clause is present in the profile.")
        else:
            missing.append("Confirm whether the business holds the registration named in the clause.")
            questions.append(f"Does the business hold the relevant registration ({', '.join(registration_terms)})?")

    industry_scope = bool(profile_industry and re.search(rf"\b(?:applies to|applicable to|shall apply to|only applies to)\b.{{0,100}}\b{re.escape(profile_industry)}\b", text))
    if industry_scope and not missing:
        return {"applicability": "APPLICABLE", "reason": "The changed clause explicitly names the profile's industry; review any missing threshold or registration facts listed below.", "conditions": conditions, "matches": matches, "exemptions": exemptions, "missing": missing, "questions": questions}
    mandatory_language = bool(re.search(r"\b(shall|must|required to|is required to)\b", text))
    if conditions and matches and not missing and (explicit_scope or mandatory_language):
        return {"applicability": "APPLICABLE", "reason": "The profile matches an explicit clause scope condition.", "conditions": conditions, "matches": matches, "exemptions": exemptions, "missing": [], "questions": []}

    # A mismatch is not an exclusion unless the clause itself states a closed scope or exemption.
    if "all entities" in text or "every entity" in text or "all companies" in text:
        return {"applicability": "APPLICABLE", "reason": "The clause expressly covers all entities/companies and the profile identifies an operating business.", "conditions": ["Universal scope stated in the clause."], "matches": ["Saved profile identifies a business entity."], "exemptions": [], "missing": missing, "questions": questions}

    missing.extend(item for item in ("Relevant business activity", "Applicable jurisdiction", "Any exclusions or transitional conditions") if item not in missing)
    if not questions:
        questions.append("Does the business perform the activity described in the changed clause or hold the registration it references?")
    return {"applicability": "NEEDS_VERIFICATION", "reason": "The available clause and profile do not establish a complete scope match or a documented exclusion.", "conditions": conditions, "matches": matches, "exemptions": exemptions, "missing": missing, "questions": questions}


def analyze_changes(changes: list[dict], profile: dict | None, metadata: dict, old_pages: list[dict], new_pages: list[dict]) -> list[dict]:
    findings = []
    for change in changes:
        scope = _scope_result(change, profile, metadata)
        evidence = validate_evidence(change, old_pages, new_pages, metadata)
        evidence_required = bool(change.get("updated_clause") or change.get("previous_clause"))
        evidence_valid = bool(evidence) or not evidence_required
        applicability = scope["applicability"] if evidence_valid else "NEEDS_VERIFICATION"
        missing = list(scope["missing"])
        if not evidence_valid:
            missing.append("The source quotation could not be verified against the extracted document pages.")
        if change.get("interpretation_error"):
            missing.append("AI interpretation was unavailable; legal significance requires human review.")
        date_source_text = str(change.get("updated_clause") or "")
        extracted_dates = _explicit_dates(date_source_text)
        effective_dates = [item for item in extracted_dates if item["kind"] == "effective_date"]
        deadline_dates = [item for item in extracted_dates if item["kind"] == "compliance_deadline"]
        effective_date = effective_dates[0]["date"] if len({item["date"] for item in effective_dates}) == 1 else (metadata.get("updated") or metadata.get("current") or {}).get("effective_date")
        deadline = change.get("deadline")
        deadline_quote = change.get("deadline_evidence")
        if not deadline and len({item["date"] for item in deadline_dates}) == 1:
            deadline = deadline_dates[0]["date"]
            deadline_quote = deadline_dates[0]["quote"]
        verified_deadline_ref = next((ref for ref in evidence if ref["source_role"] in ("updated", "current") and deadline_quote and deadline_quote.casefold() in ref["quoted_text"].casefold()), None)
        deadline_status = "VERIFIED" if deadline and deadline_quote and verified_deadline_ref else ("UNVERIFIED" if re.search(r"\b(?:deadline|within\s+\d+\s+days|due date|on or before|due by|submit by|submit\b.{0,60}\bby|no later than)\b", date_source_text, re.I) else "NOT_STATED")
        if deadline_status != "VERIFIED":
            deadline = None
        category = str(change.get("category", "Uncertain change"))
        substantive = category not in ("Editorial or formatting-only change", "Uncertain change")
        priority = "High" if applicability == "APPLICABLE" and category in ("Added obligation", "Changed deadline", "Modified obligation") else "Review" if substantive else "Low"
        if deadline_status == "VERIFIED" and applicability == "APPLICABLE":
            priority = "High"
        action = change.get("action") or _recommended_action(category, applicability)
        review_required = applicability == "NEEDS_VERIFICATION" or not evidence_valid or bool(change.get("interpretation_error"))
        finding = ChangeFinding(
            change_id=change["id"], category=category, previous_text=change.get("previous_clause"), updated_text=change.get("updated_clause"),
            summary=change.get("explanation") or "Text changed; significance requires review.", applicability=applicability,
            applicability_reason=scope["reason"], applicable_conditions=scope["conditions"], matching_business_characteristics=scope["matches"],
            exemptions=scope["exemptions"], business_impact=change.get("impact") or "Assess the operational effect of this clause.",
            required_action=action, priority=priority,
            priority_rationale="Priority follows the clause category, evidence-backed applicability, and verified deadline; alarming language alone does not raise priority.",
            publication_date=(metadata.get("updated") or metadata.get("current") or {}).get("publication_date"), effective_date=effective_date,
            compliance_deadline=deadline, deadline_status=deadline_status, evidence=evidence,
            missing_information=missing, follow_up_questions=scope["questions"], review_required=review_required,
        ).model_dump()
        findings.append(finding)
    return findings


def _recommended_action(category: str, applicability: str) -> str:
    if applicability == "NEEDS_VERIFICATION":
        return "Confirm the missing business facts against the original clause, then record the scope decision."
    if applicability == "NOT_APPLICABLE":
        return "Record the stated scope exclusion and keep the cited clause with the compliance file."
    actions = {
        "Changed reporting frequency": "Update the register review calendar to the new reporting frequency and assign an owner.",
        "Changed threshold or eligibility condition": "Check the business size and activity against the new threshold; prepare the required report if covered.",
        "Changed deadline": "Schedule the filing by the verified due date and assign someone to prepare supporting records.",
        "Changed retention period": "Update the records policy and retain the affected records for the new period.",
        "Changed responsible party": "Assign the named contact person and document their filing and recordkeeping duties.",
        "Changed effective date": "Prepare affected processes before the stated effective date; verify any separate filing deadline.",
    }
    return actions.get(category, "Review the changed clause, update the affected process, and retain completion evidence.")


def applicability_summary(findings: list[dict]) -> dict:
    counts = {key: sum(item["applicability"] == key for item in findings) for key in ("APPLICABLE", "NOT_APPLICABLE", "NEEDS_VERIFICATION")}
    return {"counts": counts, "meaningful_changes": sum(item["category"] not in ("Editorial or formatting-only change", "Unchanged clause") for item in findings),
            "generated_at": datetime.now(timezone.utc).isoformat()}


def json_list(value: list) -> str:
    return json.dumps(value, ensure_ascii=False)