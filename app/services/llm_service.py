"""LLM service — DeepSeek (OpenAI-compatible) for job extraction."""

import json

from openai import AsyncOpenAI

from app.config import settings

_client = AsyncOpenAI(
    api_key=settings.LLM_API_KEY,
    base_url=settings.LLM_BASE_URL,
)


async def extract_job_fields(raw_text: str) -> dict:
    """Extract structured job fields from a raw job description using LLM."""
    prompt = f"""Parse this job posting and return a JSON object with these fields. Return ONLY the JSON, no other text.

RULES:
- title: The job title. It is ALWAYS in the first 1-3 lines of the posting. Just grab it directly.
- company: The company name. Look for the company that is hiring - it is mentioned repeatedly throughout.
- location: The office location or list of cities. Look for "Location", city names, or country names.
- remote: true if remote/hybrid is mentioned, false otherwise.
- salary_range: The compensation if shown. Examples: "$120k-$150k", "GBP 62K - 72K", "EUR 90.000-110.000". Include currency symbol. If only "competitive salary" is stated, use "Competitive".
- tags: An array of 10-20 labels including skills, technologies, industry, seniority, and role type. E.g. ["Python", "AWS", "fintech", "senior", "backend"]

EXAMPLE OUTPUT:
{{"title":"Senior Backend Engineer","company":"Acme Corp","location":"London, UK","remote":true,"salary_range":"GBP 80K-100K","tags":["Python","AWS","Kubernetes","fintech","senior","backend"]}}

JOB POSTING:
{raw_text[:6000]}"""
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
