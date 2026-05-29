"""Resume parsing — extract text + sections from PDF/DOCX via pdfplumber & python-docx."""

from io import BytesIO

from app.models.resume import ResumeSection


async def parse_resume_bytes(filename: str, content: bytes) -> tuple[str, list[ResumeSection]]:
    """Parse resume file bytes and return raw text + structured sections."""
    ext = filename.rsplit(".", 1)[-1].lower()

    if ext == "pdf":
        return _parse_pdf(content)
    elif ext in ("docx", "doc"):
        return _parse_docx(content)
    elif ext == "txt":
        text = content.decode("utf-8", errors="replace")
        return text, _segment_sections(text)
    else:
        raise ValueError(f"Unsupported file type: .{ext}")


def _parse_pdf(content: bytes) -> tuple[str, list[ResumeSection]]:
    import pdfplumber

    full_text_parts = []
    with pdfplumber.open(BytesIO(content)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text_parts.append(text)

    full_text = "\n\n".join(full_text_parts)
    sections = _segment_sections(full_text)
    return full_text, sections


def _parse_docx(content: bytes) -> tuple[str, list[ResumeSection]]:
    from docx import Document

    doc = Document(BytesIO(content))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    full_text = "\n".join(paragraphs)
    sections = _segment_sections(full_text)
    return full_text, sections


def _segment_sections(text: str) -> list[ResumeSection]:
    """Naive section splitter — looks for ALL_CAPS or Title-Case headings."""
    lines = text.split("\n")
    sections: list[ResumeSection] = []
    current_heading = "Header"
    current_lines: list[str] = []

    # Heuristic: line is a heading if it's short (<60 chars), may be ALL CAPS or Title Case
    def is_heading(line: str) -> bool:
        stripped = line.strip()
        if len(stripped) > 60:
            return False
        if stripped.isupper() and len(stripped.split()) <= 5:
            return True
        # Title Case: every word capitalised, 2-5 words
        words = stripped.split()
        if 2 <= len(words) <= 5 and all(w[0].isupper() for w in words if w):
            return True
        return False

    for line in lines:
        if is_heading(line) and not current_lines:
            current_heading = line.strip()
        elif is_heading(line) and current_lines:
            if current_lines:
                sections.append(ResumeSection(title=current_heading, content="\n".join(current_lines)))
            current_heading = line.strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        sections.append(ResumeSection(title=current_heading, content="\n".join(current_lines)))

    return sections
