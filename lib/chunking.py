"""
Chunk Markdown and Python for RAG: markdown by header/paragraph; Python by ast (def/class).
These functions are called by ingest.py when it walks vault + repos to build the vector DB
for each file. 
"""
import ast
import re
from dataclasses import dataclass

# Target ~600 tokens; ~4 chars/token -> ~2400 chars. Overlap one paragraph.
CHUNK_MAX_CHARS = 2400
CHUNK_OVERLAP_PARAS = 1

# Chunk class for the RAG, holds a slice of the content for vector DB
# For draft, a chunk can have text, code or both
@dataclass
class Chunk:
    text: str
    repo: str
    path: str
    heading: str  # section heading or empty (e.g. function/class name for code)
    chunk_index: int
    start_line: int | None = None  # 1-based; only for code chunks
    end_line: int | None = None

# Internal function to chop markdown files into sections by headers
# TODO - revisit for decorators to handle different file types
def _split_into_sections(content: str) -> list[tuple[str, str]]:
    """Split markdown by ## or ### headers. Returns list of (heading, body)."""
    # Match ## or ### at start of line (optional leading whitespace)
    pattern = re.compile(r"^(#{2,3})\s*(.+)$", re.MULTILINE)
    # sections ["heading", "body"] 
    # where heading is extracted by (.+)$ after each ## to the endf of the line
    # body is the content between the headings
    sections: list[tuple[str, str]] = []
    last_end = 0
    current_heading = ""
    """
    Using the README.md as an example:
    pattern is an iter of (#{2,3})\\s*(.+)$ matched objects
    m.group(1) is the ## or ###
    m.group(2) is the heading. e.g. "Getting Started (quick start)"
    m.start() is the start index of the match, an integer
    m.end() is the end index of the match, an integer
    """
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
    """
    after the first two rounds of the iterations, sections looked like this:
    sections = [
    ("", "# Draft\n..."),                              # intro before first ##
    ("Get started (quickest way)", "\n..."),           # between 1st and 2nd ##
    """
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
        #use .extend() because _chunk_section returns a list of Chunks
        #an .append() would make out = [...,[chunk1,chunk2,...]], not what we want
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


def _get_line_range(lines: list[str], start_line: int, end_line: int) -> str:
    """Extract source lines (1-based inclusive)."""
    return "\n".join(lines[start_line - 1 : end_line])


def chunk_python(
    repo: str,
    path: str,
    content: str,
    chunk_max_chars: int = CHUNK_MAX_CHARS,
) -> list[Chunk]:
    """
    Chunk a Python file by top-level def/class using ast.
    - Functions/async functions: one chunk each.
    - Classes: one chunk if small; else one chunk per method (heading ClassName.method_name).
    - Class-level assignments: one chunk "ClassName (class-level)".
    - Module-level code: one chunk with heading "<module>".
    - Parse error: whole file as one chunk.
    - Returns a list of Chunks that contains python code
    """
    lines = content.splitlines()
    if not lines:
        return []

    # Abstract Syntax Tree is better than regex for parsing decorators etc py code
    # it sees the code as a tree of nodes instead of text strings
    # this makes it easier to parse the code and extract the relevant information
    try:
        tree = ast.parse(content)
    except SyntaxError:
        text = content[:chunk_max_chars] + "\n..." if len(content) > chunk_max_chars else content
        return [
            Chunk(
                text=text,
                repo=repo,
                path=path,
                heading="<module>",
                chunk_index=0,
                start_line=1,
                end_line=len(lines),
            )
        ]

    chunks: list[Chunk] = []
    module_rest: list[ast.AST] = []

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start, end = node.lineno, getattr(node, "end_lineno", node.lineno)
            text = _get_line_range(lines, start, end)
            if len(text) > chunk_max_chars:
                text = text[:chunk_max_chars] + "\n..."
            chunks.append(
                Chunk(
                    text=text,
                    repo=repo,
                    path=path,
                    heading=node.name,
                    chunk_index=len(chunks),
                    start_line=start,
                    end_line=end,
                )
            )
        elif isinstance(node, ast.ClassDef):
            start, end = node.lineno, getattr(node, "end_lineno", node.lineno)
            text = _get_line_range(lines, start, end)
            if len(text) <= chunk_max_chars:
                chunks.append(
                    Chunk(
                        text=text,
                        repo=repo,
                        path=path,
                        heading=node.name,
                        chunk_index=len(chunks),
                        start_line=start,
                        end_line=end,
                    )
                )
            else:
                # One chunk per method; class-level body in one chunk.
                methods = [
                    n
                    for n in node.body
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                ]
                other = [n for n in node.body if n not in methods]
                for child in methods:
                    s = child.lineno
                    e = getattr(child, "end_lineno", child.lineno)
                    t = _get_line_range(lines, s, e)
                    if len(t) > chunk_max_chars:
                        t = t[:chunk_max_chars] + "\n..."
                    chunks.append(
                        Chunk(
                            text=t,
                            repo=repo,
                            path=path,
                            heading=f"{node.name}.{child.name}",
                            chunk_index=len(chunks),
                            start_line=s,
                            end_line=e,
                        )
                    )
                if other:
                    first_lineno = min(n.lineno for n in other)
                    last_lineno = max(
                        getattr(n, "end_lineno", n.lineno) for n in other
                    )
                    t = _get_line_range(lines, first_lineno, last_lineno)
                    if len(t) > chunk_max_chars:
                        t = t[:chunk_max_chars] + "\n..."
                    chunks.append(
                        Chunk(
                            text=t,
                            repo=repo,
                            path=path,
                            heading=f"{node.name} (class-level)",
                            chunk_index=len(chunks),
                            start_line=first_lineno,
                            end_line=last_lineno,
                        )
                    )
        else:
            module_rest.append(node)

    if module_rest:
        first_lineno = min(n.lineno for n in module_rest)
        last_lineno = max(
            getattr(n, "end_lineno", n.lineno) for n in module_rest
        )
        t = _get_line_range(lines, first_lineno, last_lineno)
        if len(t) > chunk_max_chars:
            t = t[:chunk_max_chars] + "\n..."
        chunks.append(
            Chunk(
                text=t,
                repo=repo,
                path=path,
                heading="<module>",
                chunk_index=len(chunks),
                start_line=first_lineno,
                end_line=last_lineno,
            )
        )

    return chunks
