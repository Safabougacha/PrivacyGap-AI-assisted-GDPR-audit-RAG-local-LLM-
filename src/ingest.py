"""Step 2 - Build the legal knowledge base.

GDPR (official English text, EUR-Lex)  ->  one chunk per article
(long articles split by paragraph)  ->  local embeddings  ->  ChromaDB.

Run:  python -m src.ingest
"""
import re
import sys
from html.parser import HTMLParser

import requests

from src.config import LEGAL_DIR
from src.vectorstore import COLLECTION, get_client, get_collection

GDPR_PDF_URL = "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32016R0679"
GDPR_PAGE_URL = "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32016R0679"

# all-MiniLM-L6-v2 only reads the first ~256 tokens (~1000 characters) of a
# text. Longer chunks would be silently truncated when embedded, so we keep
# each chunk under this size.
MAX_CHARS = 900


# ---------------------------------------------------------------- 1. get text
def download_gdpr() -> None:
    """Try to download the official PDF once. EUR-Lex may block scripts."""
    target = LEGAL_DIR / "gdpr_en.pdf"
    print(f"Downloading the GDPR from EUR-Lex -> {target.name} ...")
    try:
        r = requests.get(GDPR_PDF_URL, timeout=60,
                         headers={"User-Agent": "Mozilla/5.0 (PrivacyGap research project)"})
        if r.ok and r.content[:4] == b"%PDF":
            target.write_bytes(r.content)
            print(f"OK  saved ({len(r.content) // 1024} KB)")
            return
    except requests.RequestException:
        pass
    sys.exit(
        "Automatic download failed (EUR-Lex sometimes blocks scripts).\n"
        f"Open {GDPR_PAGE_URL}\n"
        "click 'PDF' (English), save the file as data/legal/gdpr_en.pdf, then rerun."
    )


class _TextFromHTML(HTMLParser):
    """Turn EUR-Lex HTML into text, one line per paragraph/heading."""
    BLOCKS = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "table"}

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)


def load_gdpr_text() -> str:
    """Read the GDPR from data/legal/ (PDF, HTML or TXT)."""
    candidates = sorted(LEGAL_DIR.glob("gdpr*"))
    if not candidates:
        download_gdpr()
        candidates = sorted(LEGAL_DIR.glob("gdpr*"))
    path = candidates[0]
    print(f"Reading {path.name}")
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader
        return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    raw = path.read_text(encoding="utf-8", errors="ignore")
    if path.suffix.lower() in {".html", ".htm"}:
        parser = _TextFromHTML()
        parser.feed(raw)
        return "".join(parser.parts)
    return raw


# ------------------------------------------------------ 2. split into articles
HEADER = re.compile(r"Official Journal of the European Union|^L\s?\d+/\d+|^\d{1,2}\.\d{1,2}\.\d{4}$")


def parse_articles(text: str) -> list[dict]:
    """Walk the text line by line and rebuild the article structure.

    EUR-Lex layout:   CHAPTER II / Principles / Article 9 / <title> / 1. ... 2. ...
    Recitals (before 'HAVE ADOPTED THIS REGULATION') are skipped.
    """
    start = text.find("HAVE ADOPTED THIS REGULATION")
    if start != -1:
        text = text[start:]

    articles, current = [], None
    chapter, expect = "", None  # expect: which kind of title the next line is
    for line in (l.strip() for l in text.splitlines()):
        if not line or HEADER.search(line):
            continue
        if re.fullmatch(r"CHAPTER [IVXL]+", line):
            chapter, expect = line, "chapter"
            continue
        if re.fullmatch(r"Section \d+", line):
            expect = "section"
            continue
        m = re.fullmatch(r"Article (\d+)", line)
        if m:
            current = {"article": int(m.group(1)), "title": "", "chapter": chapter, "body": []}
            articles.append(current)
            expect = "article"
            continue
        if expect == "chapter":
            chapter, expect = f"{chapter} - {line}", None
            continue
        if expect == "section":
            expect = None
            continue
        if expect == "article":
            current["title"], expect = line, None
            continue
        if current:
            current["body"].append(line)

    # A PDF can repeat a number (e.g. a cross-reference on its own line):
    # keep the first, longest occurrence of each article.
    seen = {}
    for a in articles:
        if a["article"] not in seen or len(a["body"]) > len(seen[a["article"]]["body"]):
            seen[a["article"]] = a
    return [seen[k] for k in sorted(seen)]


# ------------------------------------------------------------- 3. chunking
def _split_long(text: str) -> list[str]:
    """Split text into pieces <= MAX_CHARS, cutting at sentence ends."""
    pieces, buf = [], ""
    for sentence in re.split(r"(?<=[.;:])\s+", text):
        if buf and len(buf) + len(sentence) + 1 > MAX_CHARS:
            pieces.append(buf)
            buf = sentence
        else:
            buf = f"{buf} {sentence}".strip()
    if buf:
        pieces.append(buf)
    return pieces


def chunk_article(a: dict) -> list[dict]:
    """One chunk per article, or per group of numbered paragraphs if long.

    Every chunk starts with 'GDPR Article N - title' so that, even alone,
    it says where it comes from (useful for retrieval AND for citation).
    """
    header = f"GDPR Article {a['article']} - {a['title']}"
    body = " ".join(a["body"])
    body = re.sub(r"\s+", " ", body).strip()

    # numbered paragraphs: "1. ...", "2. ..."
    paragraphs = re.split(r"(?:(?<=^)|(?<=\s))(?=\d{1,2}\.\s+[A-Z])", body)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    groups, buf = [], ""
    for p in paragraphs:
        for piece in (_split_long(p) if len(p) > MAX_CHARS else [p]):
            if buf and len(buf) + len(piece) + 1 > MAX_CHARS:
                groups.append(buf)
                buf = piece
            else:
                buf = f"{buf} {piece}".strip()
    if buf:
        groups.append(buf)

    return [
        {
            "id": f"gdpr-art{a['article']}-{i}",
            "text": f"{header}\n{g}",
            "metadata": {"source": "GDPR", "article": a["article"],
                         "title": a["title"], "chapter": a["chapter"], "part": i},
        }
        for i, g in enumerate(groups or [""], start=1)
    ]


# ------------------------------------------------------------- 4. store
def main() -> None:
    articles = parse_articles(load_gdpr_text())
    numbers = [a["article"] for a in articles]
    print(f"Parsed {len(articles)} articles (expected 99)")
    missing = sorted(set(range(1, 100)) - set(numbers))
    if missing:
        print(f"WARNING missing articles: {missing}")

    chunks = [c for a in articles for c in chunk_article(a)]
    print(f"Created {len(chunks)} chunks (max {MAX_CHARS} characters each)")

    client = get_client()
    try:  # rebuild from scratch so a rerun never duplicates chunks
        client.delete_collection(COLLECTION)
    except Exception:
        pass
    collection = get_collection(client)
    print("Embedding locally and storing in ChromaDB (about 1 minute)...")
    batch = 100
    for i in range(0, len(chunks), batch):
        part = chunks[i:i + batch]
        collection.add(ids=[c["id"] for c in part],
                       documents=[c["text"] for c in part],
                       metadatas=[c["metadata"] for c in part])
    print(f"OK  {collection.count()} chunks stored in '{COLLECTION}'")


if __name__ == "__main__":
    main()
