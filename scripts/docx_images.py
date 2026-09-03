"""Pull the question screenshots out of a .docx, in the order they appear.

The source documents are exam screenshots pasted into Word, so the questions
live in images rather than in text. Zip order is not document order -- the
archive lists media alphabetically, which puts image10 before image2 -- so this
walks the document body for drawing references and resolves them through the
relationship table. Getting that wrong silently reorders the questions, which
is the one error the whole ground-truth bank cannot absorb.

    python scripts/docx_images.py "data/documents/scoped/1. Foo.docx" -o work/1
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


def extract(path: Path, out_dir: Path) -> list[Path]:
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
    parser.add_argument("docx", type=Path)
    parser.add_argument("-o", "--out-dir", type=Path, required=True)
    args = parser.parse_args()

    written = extract(args.docx, args.out_dir)
    unreferenced = 0
    with zipfile.ZipFile(args.docx) as archive:
        total = sum(1 for n in archive.namelist() if "word/media/" in n)
    unreferenced = total - len(written)

    print(f"document  {args.docx.name}")
    print(f"images    {len(written)} in document order -> {args.out_dir}/")
    if unreferenced:
        # Word keeps orphaned media after an edit; those are not questions.
        print(f"skipped   {unreferenced} media part(s) not referenced from the body")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
