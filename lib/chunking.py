"""
Chunk Markdown into logical segments for RAG: by header and paragraph, with size cap.
"""
import re
from dataclasses import dataclass

# Target ~600 tokens; ~4 chars/token -> ~2400 chars. Overlap one paragraph.
CHUNK_MAX_CHARS = 2400
CHUNK_OVERLAP_PARAS = 1


@dataclass
class Chunk:
    text: str
    repo: str
    path: str
    heading: str  # section heading or empty
    chunk_index: int


def _split_into_sections(content: str) -> list[tuple[str, str]]:
    """Split markdown by ## or ### headers. Returns list of (heading, body)."""
    # Match ## or ### at start of line (optional leading whitespace)
    pattern = re.compile(r"^(#{2,3})\s*(.+)$", re.MULTILINE)
    sections: list[tuple[str, str]] = []
    last_end = 0
    current_heading = ""
    for m in pattern.finditer(content):
        if m.start() > last_end:
            body = content[last_end : m.start()].strip()
            if body:
                sections.append((current_heading, body))
        current_heading = m.group(2).strip()
        last_end = m.end()
    if last_end < len(content):
        body = content[last_end:].strip()
        if body:
            sections.append((current_heading, body))
    if not sections and content.strip():
        sections.append(("", content.strip()))
    return sections


def _paragraphs(text: str, chunk_max_chars: int = CHUNK_MAX_CHARS) -> list[str]:
    """Split text into paragraphs (blank-line separated)."""
    out: list[str] = []
    for p in re.split(r"\n\s*\n", text):
        p = p.strip()
        if not p:
            continue
        # Hard-split very long paragraphs so one malformed block can't create huge chunks.
        if len(p) <= chunk_max_chars:
            out.append(p)
            continue
        start = 0
        while start < len(p):
            out.append(p[start : start + chunk_max_chars])
            start += chunk_max_chars
    return out


def _chunk_section(
    repo: str,
    path: str,
    heading: str,
    body: str,
    chunk_max_chars: int = CHUNK_MAX_CHARS,
    chunk_overlap_paras: int = CHUNK_OVERLAP_PARAS,
) -> list[Chunk]:
    """Chunk a section by paragraphs, respecting CHUNK_MAX_CHARS and overlap."""
    paras = _paragraphs(body, chunk_max_chars=chunk_max_chars)
    if not paras:
        return []
    chunks: list[Chunk] = []
    current: list[str] = []
    current_len = 0
    overlap: list[str] = []

    for p in paras:
        p_len = len(p) + 2  # +2 for newline
        if current_len + p_len > chunk_max_chars and current:
            text = "\n\n".join(current)
            chunks.append(
                Chunk(
                    text=text,
                    repo=repo,
                    path=path,
                    heading=heading,
                    chunk_index=len(chunks),
                )
            )
            overlap = current[-chunk_overlap_paras:] if chunk_overlap_paras else []
            current = overlap.copy()
            current_len = sum(len(x) + 2 for x in current)
        current.append(p)
        current_len += p_len

    if current:
        text = "\n\n".join(current)
        chunks.append(
            Chunk(
                text=text,
                repo=repo,
                path=path,
                heading=heading,
                chunk_index=len(chunks),
            )
        )
    return chunks


def chunk_markdown(
    repo: str,
    path: str,
    content: str,
    chunk_max_chars: int = CHUNK_MAX_CHARS,
    chunk_overlap_paras: int = CHUNK_OVERLAP_PARAS,
) -> list[Chunk]:
    """Chunk a single markdown file. Returns list of Chunk with metadata."""
    sections = _split_into_sections(content)
    out: list[Chunk] = []
    for heading, body in sections:
        out.extend(
            _chunk_section(
                repo,
                path,
                heading,
                body,
                chunk_max_chars=chunk_max_chars,
                chunk_overlap_paras=chunk_overlap_paras,
            )
        )
    return out
