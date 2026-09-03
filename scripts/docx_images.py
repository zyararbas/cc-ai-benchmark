"""Pull the question screenshots out of a source document, in reading order.

The source documents are exam screenshots pasted into Word, so the questions
live in images rather than in text. Zip order is not document order -- the
archive lists media alphabetically, which puts image10 before image2 -- so this
walks the document body for drawing references and resolves them through the
relationship table. Getting that wrong silently reorders the questions, which
is the one error the whole ground-truth bank cannot absorb.

Handles .docx and .pdf, because documents arrive as both -- the same deck is
often supplied twice, once in each. The images are usually identical; the
formats differ only in how you get at them and in what counts as order.

    python scripts/docx_images.py "data/documents/scoped/1. Foo.docx" -o work/1
    python scripts/docx_images.py "data/documents/scoped/1. Foo.pdf"  -o work/1
"""

from __future__ import annotations

import argparse
import re
import shutil
import zipfile
from pathlib import Path

EMBED = re.compile(r'r:(?:embed|link)="([^"]+)"')
REL = re.compile(r'Id="([^"]+)"[^>]*Target="([^"]+)"')


def ordered_media(path: Path) -> list[str]:
    """Media part names in document-body order, de-duplicated."""
    with zipfile.ZipFile(path) as archive:
        document = archive.read("word/document.xml").decode("utf-8", "replace")
        rels = archive.read("word/_rels/document.xml.rels").decode("utf-8", "replace")
    target = {rid: t for rid, t in REL.findall(rels)}
    seen: list[str] = []
    for rid in EMBED.findall(document):
        part = target.get(rid)
        if not part:
            continue
        name = "word/" + part.removeprefix("/word/").removeprefix("word/")
        # The same image can be referenced twice; keep the first position.
        if "media/" in name and name not in seen:
            seen.append(name)
    return seen


def pdf_images(path: Path, out_dir: Path) -> list[Path]:
    """Page order is reading order, so no relationship table to resolve."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - optional extra
        raise RuntimeError("pypdf not installed. `pip install -e '.[pdf]'`") from exc

    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for page_no, page in enumerate(PdfReader(str(path)).pages, start=1):
        for index, image in enumerate(page.images):
            # Several images on one page keep their within-page order.
            suffix = "" if index == 0 else f"-{index}"
            destination = out_dir / f"page-{page_no:03d}{suffix}.png"
            destination.write_bytes(image.data)
            written.append(destination)
    if not written:
        raise ValueError(f"{path.name}: no embedded images")
    return written


def extract(path: Path, out_dir: Path) -> list[Path]:
    if path.suffix.lower() == ".pdf":
        return pdf_images(path, out_dir)
    names = ordered_media(path)
    if not names:
        raise ValueError(f"{path.name}: no images referenced from the document body")
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    with zipfile.ZipFile(path) as archive:
        for index, name in enumerate(names, start=1):
            suffix = Path(name).suffix or ".png"
            destination = out_dir / f"page-{index:03d}{suffix}"
            with archive.open(name) as source, destination.open("wb") as sink:
                shutil.copyfileobj(source, sink)
            written.append(destination)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("docx", type=Path, metavar="DOCUMENT", help=".docx or .pdf")
    parser.add_argument("-o", "--out-dir", type=Path, required=True)
    args = parser.parse_args()

    written = extract(args.docx, args.out_dir)
    print(f"document  {args.docx.name}")
    print(f"images    {len(written)} in reading order -> {args.out_dir}/")
    if args.docx.suffix.lower() != ".pdf":
        with zipfile.ZipFile(args.docx) as archive:
            total = sum(1 for n in archive.namelist() if "word/media/" in n)
        if total - len(written):
            # Word keeps orphaned media after an edit; those are not questions.
            print(f"skipped   {total - len(written)} media part(s) not referenced from the body")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
