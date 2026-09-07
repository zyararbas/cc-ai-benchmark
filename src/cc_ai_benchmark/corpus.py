"""The source material, for the grounded conditions.

Text is pulled straight out of the .docx zip rather than through a library: the
harness stays dependency-free, and the extraction is a dozen lines anyone can
audit. Sections are keyed by the same `ref` the bank items carry, so C1 (oracle
context) is an exact lookup rather than a search.

Documents also arrive as PDF -- the same deck reissued in another format -- and
that path does need pypdf, an optional extra. A missing document is not a
degraded corpus, it is a wrong one: every grounded answer for the items it backs
is then produced without the material the condition claims to supply. So an
unreadable source raises rather than being skipped. This module was `.docx`-only
until three documents were reissued as PDF and silently vanished from the
corpus, taking C1 for 60 items with them.
"""

from __future__ import annotations

import functools
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = REPO_ROOT / "data" / "documents" / "scoped"

_PARA = re.compile(r"</w:p>")
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t]+")
_BLANKS = re.compile(r"\n{3,}")
_WORD = re.compile(r"[a-z][a-z0-9']+")

_STOP = {
    "the",
    "and",
    "for",
    "that",
    "this",
    "with",
    "which",
    "from",
    "are",
    "was",
    "not",
    "but",
    "all",
    "any",
    "under",
    "would",
    "have",
    "has",
    "will",
    "can",
    "does",
    "following",
    "insured",
    "insurance",
    "policy",
    "coverage",
}


@dataclass(frozen=True)
class Section:
    ref: str
    scope: str
    text: str

    @property
    def approx_tokens(self) -> int:
        return len(self.text) // 4


def _tidy(text: str) -> str:
    return _BLANKS.sub("\n\n", _WS.sub(" ", text)).strip()


def _extract_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml").decode("utf-8", "ignore")
    return _tidy(_TAG.sub("", _PARA.sub("\n", xml)))


def _extract_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise RuntimeError(
            f"{path.name} is a PDF and pypdf is not installed. "
            "`pip install -e '.[pdf]'` -- without it this document is missing "
            "from the corpus and every grounded answer it backs is unsupported."
        ) from exc
    # Page order is reading order; there is no relationship table to resolve.
    pages = (page.extract_text() or "" for page in PdfReader(path).pages)
    return _tidy("\n\n".join(pages))


_EXTRACTORS = {".docx": _extract_docx, ".pdf": _extract_pdf}


@functools.lru_cache(maxsize=1)
def load_sections(directory: Path = DOCS_DIR) -> dict[str, Section]:
    """Every source document, keyed by filename -- the bank's `ref` value."""
    sections: dict[str, Section] = {}
    seen_stems: dict[str, str] = {}
    candidates = sorted(
        (p for p in directory.iterdir() if p.suffix.lower() in _EXTRACTORS),
        # .docx first within a stem: native text beats text recovered from a
        # PDF's layout, and a deck reissued as PDF is the same document twice.
        key=lambda p: (p.name.casefold(), p.suffix.lower() != ".docx"),
    )
    for path in candidates:
        if path.name.startswith("~$"):
            continue
        stem = path.stem.strip().casefold()
        if stem in seen_stems:
            continue
        seen_stems[stem] = path.name
        scope = re.sub(r"^\d+\.\s*", "", path.stem).strip()
        text = _EXTRACTORS[path.suffix.lower()](path)
        sections[path.name] = Section(ref=path.name, scope=scope, text=text)
    return sections


def _resolve(ref: str, sections: dict[str, Section]) -> Section | None:
    """Bank refs say `.pdf` or `.docx` interchangeably; match on the stem."""
    if ref in sections:
        return sections[ref]
    stem = Path(ref).stem.strip().casefold()
    for section in sections.values():
        if Path(section.ref).stem.strip().casefold() == stem:
            return section
    return None


def oracle_context(ref: str, max_chars: int | None = None) -> str | None:
    """C1: the one document an item was drawn from."""
    section = _resolve(ref, load_sections())
    if section is None:
        return None
    return section.text[:max_chars] if max_chars else section.text


def full_corpus(max_chars: int | None = None) -> str:
    """C2 with no retriever: every document, concatenated and labelled."""
    parts = [f"### {s.ref}\n\n{s.text}" for s in load_sections().values()]
    joined = "\n\n".join(parts)
    return joined[:max_chars] if max_chars else joined


def _terms(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.casefold()) if len(w) > 3 and w not in _STOP}


def retrieve(question: str, choices: dict[str, str], k: int = 1) -> list[Section]:
    """C2: the shared retriever, identical for every system under test.

    Deliberately simple and deterministic -- a term-overlap ranker with no
    embeddings, no index, and no per-system tuning. Its recall is published
    alongside results (see `recall_at_k`); a shared retriever only has to be
    fair, not good, and a transparent one is easier to hold constant.
    """
    query = _terms(question + " " + " ".join(choices.values()))
    if not query:
        return []
    scored = []
    for section in load_sections().values():
        overlap = len(query & _terms(section.text))
        scored.append((overlap / len(query), section))
    scored.sort(key=lambda pair: (-pair[0], pair[1].ref))
    return [section for _, section in scored[:k]]


def recall_at_k(items, k: int = 1) -> float:
    """Share of items whose own source document is in the retriever's top k."""
    if not items:
        return 0.0
    hits = 0
    for item in items:
        got = {Path(s.ref).stem.casefold() for s in retrieve(item.question, item.choices, k)}
        if Path(item.ref).stem.casefold() in got:
            hits += 1
    return round(hits / len(items), 4)


def context_for(item, condition: str, max_chars: int | None = 60_000) -> str | None:
    """The context a condition entitles an item to."""
    if condition == "C0":
        return None
    if condition == "C1":
        return oracle_context(item.ref, max_chars)
    if condition == "C2":
        sections = retrieve(item.question, item.choices, k=1)
        if not sections:
            return None
        return sections[0].text[:max_chars] if max_chars else sections[0].text
    return None
