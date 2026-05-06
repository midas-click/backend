"""LLM service — DeepSeek (OpenAI-compatible) for tailoring & match scoring."""

import json
from typing import Optional

from openai import AsyncOpenAI

from app.config import settings

_client = AsyncOpenAI(
    api_key=settings.LLM_API_KEY,
    base_url=settings.LLM_BASE_URL,
)


async def extract_job_fields(raw_text: str) -> dict:
    """Extract structured job fields from a raw job description using LLM."""
    prompt = f"""You are a job listing parser. Extract structured information from the raw job description below.
Return ONLY a valid JSON object with these fields (use null for missing values):
- title: the job title
- company: the company name
- location: office location or city/state
- remote: boolean, true if remote/hybrid mentioned
- salary_range: salary range if mentioned (e.g. "$120k-$150k")
- keywords: array of 10-20 key skills, technologies, tools mentioned
- tags: array of 3-5 categories like industry, seniority, role type (e.g. ["fintech", "senior", "backend"])

Job description:
{raw_text[:5000]}
"""
    resp = await _client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1000,
        temperature=0.2,
    )
    raw = resp.choices[0].message.content or "{}"
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        import re
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return {"title": "Untitled", "company": "Unknown"}


async def extract_keywords_from_job(job_description: str) -> list[str]:
    """Extract a ranked list of keywords from a job description."""
    prompt = f"""You are a resume expert. Extract the top 15-20 most important keywords (skills,
certifications, technologies, tools, soft skills, degrees, experience levels) from this job description.
Return ONLY a JSON array of strings, nothing else.

Job description:
{job_description[:4000]}
"""
    resp = await _client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=400,
        temperature=0.2,
    )
    raw = resp.choices[0].message.content or "[]"
    # Try to extract JSON array from possible markdown wrapping
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        import re
        match = re.search(r"\[.*?\]", raw, re.DOTALL)
        if match:
            return json.loads(match.group())
        return []


async def generate_tailored_resume(
    base_resume_text: str,
    job_description: str,
    missing_keywords: list[str],
) -> str:
    """Generate a tailored version of the resume that incorporates missing keywords naturally."""
    prompt = f"""You are a professional resume writer. Given a base resume and a job description, rewrite
the resume to incorporate the following MISSING KEYWORDS naturally into the existing experience,
skills, and summary sections. Do NOT fabricate experiences or jobs — only rephrase and emphasize
existing content to match the job. Preserve the original structure and company names.

=== BASE RESUME ===
{base_resume_text[:5000]}

=== JOB DESCRIPTION ===
{job_description[:4000]}

=== KEYWORDS TO INCORPORATE ===
{", ".join(missing_keywords)}

Return ONLY the tailored resume text. Do not include explanations.
"""
    resp = await _client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=3000,
        temperature=0.5,
    )
    return resp.choices[0].message.content or base_resume_text


async def compute_match_score(
    resume_text: str,
    job_description: str,
    job_keywords: list[str],
) -> tuple[float, str]:
    """Return match score (0-100) + human-readable explanation."""
    prompt = f"""You are an ATS analyst. Compare the candidate's resume against the job description and
calculate a match score from 0 to 100. Then write a concise explanation (3-5 sentences) covering:
- Which key skills match well
- Which are missing or weak
- Overall fit assessment

Return valid JSON: {{"score": <number>, "explanation": "<text>"}}

=== RESUME ===
{resume_text[:5000]}

=== JOB DESCRIPTION ===
{job_description[:4000]}

=== KEY EXTRACTED KEYWORDS ===
{", ".join(job_keywords[:20])}
"""
    resp = await _client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=500,
        temperature=0.3,
    )
    raw = resp.choices[0].message.content or "{}"
    try:
        data = json.loads(raw)
        return float(data.get("score", 50)), str(data.get("explanation", ""))
    except (json.JSONDecodeError, ValueError):
        return 50.0, "Could not compute match."


async def generate_interview_questions(
    job_description: str,
    role: str = "",
) -> dict:
    """Generate likely interview questions categorised by type."""
    prompt = f"""You are an interview coach. Based on this job description, generate 8-12 likely
interview questions. Categorise them as "behavioral", "technical", or "role_specific".

Job: {role}
{job_description[:3000]}

Return JSON: {{"behavioral": ["..."], "technical": ["..."], "role_specific": ["..."]}}
"""
    resp = await _client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1000,
        temperature=0.7,
    )
    raw = resp.choices[0].message.content or "{}"
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"behavioral": [], "technical": [], "role_specific": []}
