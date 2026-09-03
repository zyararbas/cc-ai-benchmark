"""Tests for document ingestion: image order, reconciliation, id stability."""

import json
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from docx_images import ordered_media  # noqa: E402
from reconcile_extraction import normalize, reconcile  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _docx(tmp_path: Path, order: list[int]) -> Path:
    """A minimal .docx whose body references media in `order`."""
    path = tmp_path / "doc.docx"
    body = "".join(f'<w:drawing><a:blip r:embed="rId{n}"/></w:drawing>' for n in order)
    unique = sorted(set(order))
    rels = "".join(f'<Relationship Id="rId{n}" Target="media/image{n}.png"/>' for n in unique)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", f"<w:document><w:body>{body}</w:body></w:document>")
        archive.writestr("word/_rels/document.xml.rels", f"<Relationships>{rels}</Relationships>")
        for n in unique:
            archive.writestr(f"word/media/image{n}.png", PNG)
    return path


def test_images_come_back_in_document_order_not_archive_order(tmp_path):
    """Archive order sorts image10 before image2; the reader does not."""
    path = _docx(tmp_path, [2, 10, 1])
    assert ordered_media(path) == [
        "word/media/image2.png",
        "word/media/image10.png",
        "word/media/image1.png",
    ]


def test_a_repeated_image_keeps_its_first_position(tmp_path):
    assert ordered_media(_docx(tmp_path, [3, 1, 3])) == [
        "word/media/image3.png",
        "word/media/image1.png",
    ]


@pytest.mark.parametrize(
    "a,b",
    [
        ("What is risk?", "what   is RISK?"),
        ("Define peril.", "Define peril"),
        ("A, B and C", "A B and C"),
    ],
)
def test_normalize_matches_cosmetic_rewrites_only(a, b):
    assert normalize(a) == normalize(b)


def test_normalize_does_not_collapse_different_questions():
    assert normalize("What is risk?") != normalize("What is peril?")


def _item(seq, question, answer="A", choices=None):
    return {
        "id": f"q_{seq}",
        "question": question,
        "choices": choices or {"A": "x", "B": "y"},
        "answer": answer,
    }


def test_a_moved_question_keeps_its_id_and_its_line():
    """Position in the document is not identity; position in the file is."""
    old = [_item(1, "First"), _item(2, "Second")]
    new = [_item(1, "Second"), _item(2, "First")]
    result = reconcile(old, new)
    assert result["counts"]["MOVED"] == 2
    assert [r["id"] for r in result["merged"]] == ["q_1", "q_2"]
    assert result["merged"][0]["question"] == "First"


def test_a_removed_question_is_tombstoned_so_later_ids_do_not_shift():
    old = [_item(1, "Keep"), _item(2, "Drop"), _item(3, "Also keep")]
    new = [_item(1, "Keep"), _item(2, "Also keep")]
    merged = reconcile(old, new)["merged"]
    assert [r["id"] for r in merged] == ["q_1", "q_2", "q_3"]
    assert merged[1]["retired"] is True
    # The third question must still be the third line, or the bank renames it.
    assert merged[2]["question"] == "Also keep"
    assert not merged[2].get("retired")


def test_a_changed_answer_retires_the_old_item_rather_than_mutating_it():
    """Models were scored against the old key; the two are not one item."""
    old = [_item(1, "Stem", answer="A")]
    new = [_item(1, "Stem", answer="B")]
    result = reconcile(old, new)
    assert result["counts"]["EDITED"] == 1
    assert result["counts"]["ADDED"] == 1
    merged = result["merged"]
    assert merged[0]["retired"] is True and merged[0]["answer"] == "A"
    assert merged[1]["id"] == "q_2" and merged[1]["answer"] == "B"


def test_new_questions_append_and_never_reuse_a_retired_id():
    old = [_item(1, "Gone"), _item(2, "Stays")]
    new = [_item(1, "Stays"), _item(2, "Brand new")]
    merged = reconcile(old, new)["merged"]
    assert [r["id"] for r in merged] == ["q_1", "q_2", "q_3"]
    assert merged[0]["retired"] is True
    assert merged[2]["question"] == "Brand new"


def test_build_bank_skips_tombstones_without_shifting_sequence(tmp_path):
    from cc_ai_benchmark.bank import build_bank

    records = [
        _item(1, "First"),
        {**_item(2, "Retired one"), "retired": True},
        _item(3, "Third"),
    ]
    for record in records:
        record.update(scope="S", ref="9. S.docx")
    path = tmp_path / "scoped_questions_9.json"
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")

    items = build_bank(raw_dir=tmp_path, audit_path=tmp_path / "missing.json")
    assert [i.id for i in items] == ["pc-09-0001", "pc-09-0003"]
    assert items[1].question == "Third"


def test_pdf_route_reports_a_missing_dependency_rather_than_crashing(tmp_path, monkeypatch):
    """The PDF extra is optional; its absence must be a message, not a traceback."""
    import builtins

    import docx_images

    real_import = builtins.__import__

    def no_pypdf(name, *args, **kwargs):
        if name == "pypdf":
            raise ImportError("no pypdf")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_pypdf)
    path = tmp_path / "doc.pdf"
    path.write_bytes(b"%PDF-1.4\n")
    with pytest.raises(RuntimeError, match=r"pypdf not installed"):
        docx_images.extract(path, tmp_path / "out")


def test_duplicate_audit_ignores_tombstones(tmp_path):
    """A retired question must not resurface as a duplicate of its replacement."""
    import audit_duplicates

    live = {
        "id": "q_2",
        "question": "What is a peril?",
        "choices": {"A": "cause", "B": "condition"},
        "answer": "A",
        "scope": "S",
    }
    dead = {**live, "id": "q_1", "retired": True}
    path = tmp_path / "scoped_questions_1.json"
    path.write_text(json.dumps(dead) + "\n" + json.dumps(live) + "\n", encoding="utf-8")

    items = audit_duplicates.load(tmp_path)
    assert [i["id"] for i in items] == ["q_2"]
