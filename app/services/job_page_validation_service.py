"""Rule-based validation for pages submitted as job descriptions."""

from dataclasses import dataclass, field
from urllib.parse import urlparse


@dataclass(frozen=True)
class JobPageValidationResult:
    is_job_page: bool
    confidence: float
    reason: str
    signals: list[str] = field(default_factory=list)


JOB_BOARD_DOMAINS = {
    "ashbyhq.com",
    "bamboohr.com",
    "boards.greenhouse.io",
    "careers.microsoft.com",
    "careers.google.com",
    "greenhouse.io",
    "indeed.com",
    "jobs.ashbyhq.com",
    "jobs.lever.co",
    "jobs.smartrecruiters.com",
    "applytojob.com",
    "icims.com",
    "jobvite.com",
    "linkedin.com",
    "myworkdayjobs.com",
    "recruitee.com",
    "smartrecruiters.com",
    "workable.com",
}

JOB_SECTION_PHRASES = {
    "about the role",
    "about this role",
    "about the job",
    "about the team",
    "job summary",
    "role overview",
    "responsibilities",
    "what you'll do",
    "what you will do",
    "you will",
    "what we're looking for",
    "what we are looking for",
    "who you are",
    "qualifications",
    "requirements",
    "minimum qualifications",
    "preferred qualifications",
    "nice to have",
    "skills",
    "experience",
    "benefits",
    "perks",
    "compensation",
    "salary",
}

JOB_ACTION_PHRASES = {
    "apply now",
    "apply for this job",
    "submit application",
    "submit your application",
    "job description",
    "job details",
    "job type",
    "employment type",
    "full-time",
    "part-time",
    "contract",
    "remote",
    "hybrid",
    "onsite",
    "equal opportunity",
}

HIRING_TERMS = {
    "engineer",
    "developer",
    "manager",
    "designer",
    "analyst",
    "specialist",
    "coordinator",
    "associate",
    "director",
    "architect",
    "consultant",
    "representative",
    "sales",
    "executive",
    "technician",
    "administrator",
    "lead",
    "senior",
    "intern",
    "recruiter",
    "candidate",
    "applicant",
    "interview",
    "hiring",
}

NEGATIVE_PHRASES = {
    "add to cart",
    "add to bag",
    "shopping cart",
    "checkout",
    "customer reviews",
    "product details",
    "product description",
    "related products",
    "subscribe to our newsletter",
    "leave a comment",
    "comments",
    "share this article",
    "read more",
    "privacy policy",
    "terms of service",
}

MIN_TEXT_LENGTH = 450
JOB_PAGE_THRESHOLD = 0.55


def validate_job_page(raw_text: str, source_url: str | None = None) -> JobPageValidationResult:
    text = _normalize_text(raw_text)
    signals: list[str] = []
    score = 0.0
    known_job_domain = _is_known_job_domain(source_url)

    if known_job_domain:
        score += 0.3
        signals.append("known job board domain")

    if len(text) >= MIN_TEXT_LENGTH:
        score += 0.15
        signals.append("enough page text")
    elif len(text) >= 180:
        score += 0.05
        signals.append("some page text")
    else:
        signals.append("page text is too short")

    section_matches = _count_matches(text, JOB_SECTION_PHRASES)
    if section_matches:
        score += min(0.25, section_matches * 0.05)
        signals.append(f"{section_matches} job section signals")

    action_matches = _count_matches(text, JOB_ACTION_PHRASES)
    if action_matches:
        score += min(0.2, action_matches * 0.04)
        signals.append(f"{action_matches} application/detail signals")

    hiring_matches = _count_matches(text, HIRING_TERMS)
    if hiring_matches:
        score += min(0.15, hiring_matches * 0.025)
        signals.append(f"{hiring_matches} hiring terms")

    if _has_salary_signal(text):
        score += 0.08
        signals.append("salary or compensation signal")

    if _has_location_signal(text):
        score += 0.05
        signals.append("location or remote signal")

    negative_matches = _count_matches(text, NEGATIVE_PHRASES)
    if negative_matches:
        score -= min(0.35, negative_matches * 0.07)
        signals.append(f"{negative_matches} non-job page signals")

    confidence = max(0.0, min(1.0, round(score, 2)))
    signal_count = section_matches + action_matches + hiring_matches
    has_required_content = (
        len(text) >= MIN_TEXT_LENGTH
        or section_matches + action_matches >= 3
        or (known_job_domain and len(text) >= 180 and signal_count >= 2)
    )
    threshold = 0.45 if known_job_domain else JOB_PAGE_THRESHOLD
    is_job_page = confidence >= threshold and has_required_content
    reason = (
        "Page looks like a job description"
        if is_job_page
        else "This page does not look like a job description"
    )
    return JobPageValidationResult(
        is_job_page=is_job_page,
        confidence=confidence,
        reason=reason,
        signals=signals,
    )


def _normalize_text(text: str) -> str:
    return " ".join((text or "").lower().split())


def _count_matches(text: str, phrases: set[str]) -> int:
    return sum(1 for phrase in phrases if phrase in text)


def _is_known_job_domain(source_url: str | None) -> bool:
    if not source_url:
        return False
    try:
        hostname = urlparse(source_url).hostname or ""
    except ValueError:
        return False
    hostname = hostname.lower().removeprefix("www.")
    return any(hostname == domain or hostname.endswith(f".{domain}") for domain in JOB_BOARD_DOMAINS)


def _has_salary_signal(text: str) -> bool:
    return "$" in text or "salary" in text or "compensation" in text or "pay range" in text


def _has_location_signal(text: str) -> bool:
    return "location" in text or "remote" in text or "hybrid" in text or "onsite" in text
