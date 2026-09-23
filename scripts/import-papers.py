# /// script
# requires-python = ">=3.11"
# dependencies = ["beautifulsoup4==4.14.3"]
# ///
"""Import a local paper library: uv run scripts/import-papers.py ../library."""

import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
from xml.etree import ElementTree

from bs4 import BeautifulSoup, Comment


ROOT = Path(__file__).resolve().parent.parent
ALLOWED_TAGS = set("section div span p h2 h3 h4 h5 ul ol li strong b em i code pre blockquote a br hr figure figcaption img table thead tbody tfoot tr th td caption sup sub cite details summary dl dt dd math semantics annotation mi mn mo mrow msub msup msubsup mfrac msqrt mroot munder mover munderover mtext mspace mtable mtr mtd mstyle mphantom mpadded".split())
ALLOWED_ATTRIBUTES = set("class id title lang role aria-label aria-hidden colspan rowspan scope encoding display mathvariant stretchy fence separator accent accentunder columnalign rowalign columnspacing rowspacing".split())
IMAGE_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif", "image/svg+xml": ".svg"}


def text(node):
    return " ".join(node.stripped_strings) if node else ""


def plain(value):
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    return str(value or "").strip()


def external_url(value):
    parsed = urlsplit(str(value or ""))
    return str(value) if parsed.scheme == "https" and parsed.netloc else ""


def header_field(soup, label):
    for field in soup.select("header .k"):
        if text(field).lower() == label.lower():
            content = text(field.parent)
            return content[len(text(field)):].strip()
    return ""


def clean_main(main, folder, assets):
    # Native MathML retains formulas without shipping a second copy of KaTeX's
    # visual spans or its page-specific styles.
    for formula in main.select(".katex"):
        math = formula.find("math")
        if math:
            formula.replace_with(math.extract())
    for element in list(main.find_all(["script", "style", "iframe", "object", "embed", "form", "input", "button", "link", "meta", "base"])):
        element.decompose()
    for comment in main.find_all(string=lambda value: isinstance(value, Comment)):
        comment.extract()
    for element in list(main.find_all(True)):
        if element.name not in ALLOWED_TAGS:
            element.unwrap()
            continue
        attrs = {key: value for key, value in element.attrs.items() if key in ALLOWED_ATTRIBUTES}
        if element.name == "a":
            href = str(element.get("href", ""))
            if href.startswith("#") or external_url(href):
                attrs["href"] = href
                if external_url(href):
                    attrs["rel"] = "noopener noreferrer"
            else:
                element.unwrap()
                continue
        if element.name == "img":
            src = str(element.get("src", ""))
            if src.startswith("data:"):
                header, encoded = src.split(",", 1)
                mime = header[5:].split(";", 1)[0]
                if mime not in IMAGE_TYPES or not header.endswith(";base64"):
                    raise ValueError(f"Unsupported embedded image in {folder.name}")
                data = base64.b64decode(re.sub(r"\s", "", encoded), validate=True)
                extension = IMAGE_TYPES[mime]
            else:
                local = (folder / src).resolve()
                if not local.is_relative_to(folder.resolve()) or not local.is_file():
                    raise ValueError(f"Image outside paper folder: {folder.name}: {src}")
                extension = local.suffix.lower()
                if extension not in IMAGE_TYPES.values():
                    raise ValueError(f"Unsupported image: {src}")
                data = local.read_bytes()
            name = hashlib.sha256(data).hexdigest() + extension
            if extension == ".svg":
                if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
                    raise ValueError(f"SVG declarations are not supported: {folder.name}")
                svg = ElementTree.fromstring(data)
                for node in svg.iter():
                    if node.tag.rsplit("}", 1)[-1].lower() in ("script", "foreignobject", "iframe", "style"):
                        raise ValueError(f"Active SVG content: {folder.name}")
                    for key, value in node.attrib.items():
                        key = key.rsplit("}", 1)[-1].lower()
                        if key.startswith("on") or (key in ("href", "src") and not value.startswith("#")):
                            raise ValueError(f"Active SVG attribute: {folder.name}")
            assets[name] = data
            attrs.update(src=f"/paper-assets/{name}", alt=str(element.get("alt", "논문의 그림 또는 표")), loading="lazy", decoding="async")
        element.attrs = attrs
    # Headings already have chapter IDs on their containing sections.
    headings = []
    for number, heading in enumerate(main.find_all("h2"), 1):
        section = heading.find_parent("section")
        anchor = section.get("id") if section else None
        if not anchor:
            anchor = f"section-{number}"
            heading["id"] = anchor
        headings.append({"id": anchor, "text": text(heading)})
    body = "\n".join(str(child) for child in main.contents).strip()
    return "\n".join(line.rstrip(" \t") for line in body.splitlines()) + "\n", headings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("library", type=Path)
    args = parser.parse_args()
    library = args.library.resolve()
    index = json.loads((library / "index.json").read_text())
    indexed = {record["arxiv_id"]: record for record in index["papers"]}
    topics = json.loads((ROOT / "src/data/paper-topics.json").read_text())
    topic_by_id = {}
    for topic in topics:
        for paper_id in topic["papers"]:
            if paper_id in topic_by_id:
                raise ValueError(f"Paper appears in multiple topics: {paper_id}")
            topic_by_id[paper_id] = topic["id"]

    notes, contents, assets, skipped = [], {}, {}, []
    for folder in sorted(path for path in library.iterdir() if path.is_dir()):
        html = folder / "explanation-ko.html"
        pdf = folder / "original.pdf"
        if not html.exists():
            if pdf.exists():
                with pdf.open("rb") as stream:
                    reason = "missing-explanation" if stream.read(5) == b"%PDF-" else "invalid-pdf"
                skipped.append({"id": folder.name, "reason": reason})
            continue
        if folder.name not in topic_by_id:
            raise ValueError(f"Classify the paper before publishing: {folder.name}")
        if not pdf.exists():
            raise ValueError(f"Missing source PDF: {folder.name}")
        with pdf.open("rb") as stream:
            if stream.read(5) != b"%PDF-":
                raise ValueError(f"Invalid source PDF: {folder.name}")
        metadata = {**indexed.get(folder.name, {})}
        if (folder / "metadata.json").exists():
            metadata.update(json.loads((folder / "metadata.json").read_text()))
        soup = BeautifulSoup(html.read_text(), "html.parser")
        source_url = external_url(metadata.get("arxiv_url") or metadata.get("source_url"))
        if not source_url and metadata.get("doi"):
            source_url = "https://doi.org/" + metadata["doi"]
        if not source_url:
            raise ValueError(f"Missing public source: {folder.name}")
        title = re.sub(r"\s*—\s*(챕터별 한글 해설|한국어 해설)$", "", text(soup.title))
        intro = text(soup.select_one("header.hero p"))
        summary = plain(metadata.get("one_line_conclusion") or metadata.get("conclusion")) or intro
        if len(summary) > 260:
            summary = summary[:257].rstrip() + "…"
        original_title = text(soup.select_one("h1 .en")) or metadata.get("title", title)
        authors = metadata.get("authors") or header_field(soup, "Authors")
        authors = " · ".join(authors) if isinstance(authors, list) else plain(authors)
        venue = plain(metadata.get("venue")) or text(soup.select_one("header .venue"))
        practical = plain(metadata.get("practical_implications"))
        key_points = [text(node) for node in soup.select("#take .take .body")]
        collected = str(metadata.get("selected_date", "2026-09-23"))[:10]
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", collected):
            raise ValueError(f"Invalid collection date: {folder.name}")
        body = soup.find("main")
        if not body or not title or not intro:
            raise ValueError(f"Incomplete explanation: {folder.name}")
        cleaned, headings = clean_main(body, folder, assets)
        contents[folder.name] = cleaned
        notes.append({
            "id": folder.name, "topic": topic_by_id[folder.name], "title": title,
            "originalTitle": original_title, "summary": summary, "intro": intro,
            "authors": authors, "venue": venue, "sourceUrl": source_url,
            "pdfUrl": external_url(metadata.get("pdf_url")), "collectedOn": collected,
            "tags": metadata.get("tags") or metadata.get("topic_tags") or [],
            "practical": practical, "keyPoints": key_points, "headings": headings,
        })
    if set(contents) != set(topic_by_id):
        raise ValueError(f"Classified papers without publishable content: {set(topic_by_id) - set(contents)}")

    output = ROOT / "src/content/papers"
    images = ROOT / "public/paper-assets"
    output.mkdir(parents=True, exist_ok=True)
    images.mkdir(parents=True, exist_ok=True)
    for paper_id, body in contents.items():
        (output / f"{paper_id}.html").write_text(body)
    for name, data in assets.items():
        path = images / name
        if not path.exists():
            path.write_bytes(data)
    # Only prune outputs owned by this importer.
    for path in output.glob("*.html"):
        if path.stem not in contents:
            path.unlink()
    for path in images.iterdir():
        if re.fullmatch(r"[0-9a-f]{64}\.(png|jpg|webp|gif|svg)", path.name) and path.name not in assets:
            path.unlink()
    notes.sort(key=lambda note: (note["collectedOn"], note["id"]), reverse=True)
    (ROOT / "src/data/papers.json").write_text(json.dumps(notes, ensure_ascii=False, indent=2) + "\n")
    report = {"published": len(notes), "figures": len(assets), "figureBytes": sum(map(len, assets.values())), "skipped": skipped}
    (ROOT / "scripts/paper-import-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
