"""Remove the question screenshots from a source PDF, keeping its content slides.

The scoped PDFs are the corpus the grounded conditions read from, so whatever
is in them is what a system under test is handed as source material. A question
screenshot carries its own answer key -- a green checkmark next to the right
option -- and leaving those in the document means C1 supplies the answer rather
than the material the answer is derived from. Text extraction does not see
inside an image, so the leak is invisible until something with vision reads the
same file, and by then every grounded number is unexplainable.

So once a document's questions are extracted, its question images come out and
its content slides stay. Images are named as `scripts/docx_images.py` writes
them -- `page-<page>-<index>`, both from the triage step -- so the list of
keepers is the same list that step already produced:

    python scripts/strip_question_images.py "data/documents/scoped/5. Foo.pdf" \
        --keep 2-00 2-01 6-00 --backup data/documents/work/5/original-with-images.pdf

The backup is the only remaining copy of the stripped images, and it lands in
`data/documents/work/`, which is gitignored -- so it is not recoverable from
git either. Write it before running this, not after.
"""

from __future__ import annotations

import argparse
import re
import shutil
from io import BytesIO
from pathlib import Path


def image_names(page) -> list[str]:
    """XObject names of the page's images, in the order docx_images.py numbers them."""
    return [f"/{image.name.rsplit('.', 1)[0]}" for image in page.images]


def strip(pdf_path: Path, keep: set[tuple[int, int]], out_path: Path) -> dict[str, int]:
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import ArrayObject

    writer = PdfWriter(clone_from=str(pdf_path))
    removed = kept = 0

    for page_no, page in enumerate(writer.pages, start=1):
        names = image_names(page)
        if not names:
            continue
        drop = []
        for index, name in enumerate(names):
            if (page_no, index) in keep:
                kept += 1
            else:
                drop.append(name)
        if not drop:
            continue
        removed += len(drop)

        resources = page["/Resources"].get_object()
        xobjects = resources["/XObject"].get_object()
        for name in drop:
            del xobjects[name]

        # A `/Name Do` left behind points at a resource that is gone. Readers
        # mostly shrug, but "mostly" is not a property to build a corpus on.
        pattern = re.compile("|".join(rf"{re.escape(n)} Do\n?" for n in drop))
        contents = page["/Contents"].get_object()
        # /Contents is one stream or an array of them; a `Do` can be in any.
        streams = list(contents) if isinstance(contents, ArrayObject) else [contents]
        for stream in streams:
            stream = stream.get_object()
            data = stream.get_data().decode("latin-1")
            stream.set_data(pattern.sub("", data).encode("latin-1"))

    # Dropping the reference is not dropping the image: the XObject stays in
    # the file as an orphan, so the screenshots are still in there for anything
    # that walks objects instead of pages, and the file gets BIGGER. Rebuilding
    # from the pages carries only what a page still reaches, which is the point.
    buffer = BytesIO()
    writer.write(buffer)
    buffer.seek(0)
    compacted = PdfWriter()
    compacted.append(PdfReader(buffer))

    # Write through a temporary file so an interrupted run cannot leave the
    # source truncated -- there is no second copy of a stripped document.
    temporary = out_path.with_suffix(".stripping.pdf")
    compacted.write(str(temporary))
    temporary.replace(out_path)
    return {"removed": removed, "kept": kept}


def parse_keep(values: list[str]) -> set[tuple[int, int]]:
    keep = set()
    for value in values:
        match = re.fullmatch(r"(\d+)-(\d+)", value)
        if not match:
            raise SystemExit(f"--keep takes `page-index` (e.g. 2-00), not {value!r}")
        keep.add((int(match.group(1)), int(match.group(2))))
    return keep


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path, help="the scoped PDF to strip, edited in place")
    parser.add_argument(
        "--keep",
        nargs="*",
        default=[],
        metavar="PAGE-INDEX",
        help="content slides to leave in place, named as docx_images.py numbers them",
    )
    parser.add_argument(
        "--backup",
        type=Path,
        required=True,
        help="where to copy the untouched original first -- the only copy of the images",
    )
    args = parser.parse_args()

    if args.backup.exists():
        raise SystemExit(f"{args.backup} already exists; refusing to overwrite the only original")
    args.backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(args.pdf, args.backup)

    counts = strip(args.pdf, parse_keep(args.keep), args.pdf)
    print(f"document  {args.pdf.name}")
    print(f"backup    {args.backup}")
    print(f"removed   {counts['removed']} question image(s)")
    print(f"kept      {counts['kept']} content slide(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
