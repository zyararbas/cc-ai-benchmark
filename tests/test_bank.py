"""Tests for bank assembly and corpus loading.

Both fixes these cover started as silent failures: a source document that
stopped being read, and a question file that was never read at all. Neither
raised anything -- the corpus simply got smaller and the bank simply stayed
short, which is why they are pinned here.
"""

import json
import zipfile
from pathlib import Path

import pytest

from cc_ai_benchmark.bank import GENERAL_SCOPE, build_bank, select
from cc_ai_benchmark.corpus import load_sections


def _docx(path: Path, text: str) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "word/document.xml",
            f"<w:document><w:body><w:p>{text}</w:p></w:body></w:document>",
        )
    return path


def _pdf(path: Path) -> Path:
    pypdf = pytest.importorskip("pypdf")
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with path.open("wb") as handle:
        writer.write(handle)
    return path


def _questions(path: Path, rows: list[dict]) -> Path:
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return path


def _row(qid: str, answer: str = "A", **extra) -> dict:
    return {
        "id": qid,
        "question": f"question {qid}?",
        "choices": {"A": "first", "B": "second", "C": "third", "D": "fourth"},
        "answer": answer,
        **extra,
    }


# --- corpus ---


def test_a_pdf_source_document_is_part_of_the_corpus(tmp_path):
    """The regression: `*.docx` globbing dropped three reissued documents."""
    _docx(tmp_path / "1. Alpha.docx", "alpha body")
    _pdf(tmp_path / "2. Beta.pdf")
    load_sections.cache_clear()
    sections = load_sections(tmp_path)
    assert set(sections) == {"1. Alpha.docx", "2. Beta.pdf"}


def test_one_document_in_two_formats_is_one_section(tmp_path):
    """A deck reissued as PDF is the same document, and .docx text wins."""
    _docx(tmp_path / "1. Alpha.docx", "native text")
    _pdf(tmp_path / "1. Alpha.pdf")
    load_sections.cache_clear()
    sections = load_sections(tmp_path)
    assert list(sections) == ["1. Alpha.docx"]
    assert "native text" in sections["1. Alpha.docx"].text


def test_the_real_corpus_gives_every_bank_item_an_oracle_document():
    """C1 is only a condition if every item has the document it was drawn from."""
    from cc_ai_benchmark.corpus import oracle_context

    load_sections.cache_clear()
    orphans = [i.id for i in build_bank() if not i.ref or not oracle_context(i.ref)]
    assert orphans == [i.id for i in build_bank() if "no-source" in i.flags]


# --- bank ---


def _raw_dir(tmp_path: Path) -> Path:
    raw = tmp_path / "questions"
    raw.mkdir()
    _questions(
        raw / "scoped_questions_1.json",
        [_row("q_1", scope="Contracts", ref="1. Contracts.docx")],
    )
    _questions(raw / "questions_1.json", [_row("q_1", "B"), _row("q_2", "C")])
    return raw


def test_general_questions_are_in_the_bank(tmp_path):
    """`questions_*.json` was never globbed, so 99 items had never been asked."""
    items = build_bank(_raw_dir(tmp_path), tmp_path / "missing.json")
    general = [i for i in items if i.scope == GENERAL_SCOPE]
    assert len(general) == 2
    assert len(items) == 3


def test_general_ids_cannot_collide_with_scoped_ids(tmp_path):
    """Both files are `_1`; only the namespace keeps their line 1 apart."""
    items = build_bank(_raw_dir(tmp_path), tmp_path / "missing.json")
    ids = [i.id for i in items]
    assert ids == ["pc-01-0001", "pc-gen01-0001", "pc-gen01-0002"]
    assert len(set(ids)) == len(ids)


def test_an_item_with_no_source_document_says_so(tmp_path):
    """Left to an empty ref, a caller would grade an oracle run it never had."""
    items = build_bank(_raw_dir(tmp_path), tmp_path / "missing.json")
    flagged = {i.id: i.flags for i in items}
    assert "no-source" not in flagged["pc-01-0001"]
    assert "no-source" in flagged["pc-gen01-0001"]


def test_the_glob_for_general_files_does_not_swallow_scoped_ones(tmp_path):
    """`questions_*.json` and `scoped_questions_*.json` must stay disjoint."""
    items = build_bank(_raw_dir(tmp_path), tmp_path / "missing.json")
    scoped = [i for i in items if i.scope == "Contracts"]
    assert len(scoped) == 1
    assert scoped[0].source == "scoped_questions_1.json:q_1"


def test_a_retired_uid_is_dropped_without_renumbering_the_rest(tmp_path):
    raw = _raw_dir(tmp_path)
    audit = tmp_path / "audit.json"
    audit.write_text(json.dumps({"retire_uids": ["questions_1.json:q_1"]}), encoding="utf-8")
    items = build_bank(raw, audit)
    assert [i.id for i in items] == ["pc-01-0001", "pc-gen01-0002"]


def test_stratified_sampling_covers_the_general_scope():
    """The general bucket is one scope of 24; a sample must not miss it."""
    items = build_bank()
    picked = select(items, sample=200, seed=0)
    assert len(picked) == 200
    assert any(i.scope == GENERAL_SCOPE for i in picked)


def test_an_unreadable_marker_is_flagged_not_silently_graded(tmp_path):
    """A null key matches no letter, so an unflagged item scores every model wrong."""
    raw = tmp_path / "questions"
    raw.mkdir()
    _questions(
        raw / "scoped_questions_1.json",
        [
            _row("q_1", scope="Contracts", ref="1. Contracts.docx"),
            {
                **_row("q_2", scope="Contracts", ref="1. Contracts.docx"),
                "answer": None,
                "needs_review": True,
                "review_note": "marker column clipped",
            },
        ],
    )
    items = build_bank(raw, tmp_path / "missing.json")
    flagged = {i.id: i.flags for i in items}
    assert "needs-review" not in flagged["pc-01-0001"]
    assert "needs-review" in flagged["pc-01-0002"]
    assert [i.id for i in select(items)] == ["pc-01-0001"]
