"""
Ingests the postmortem markdown files into a local vector store.

This is the part of a RAG system that actually decides retrieval quality, and
it is the part most demos skip past. Three decisions are made here, and all
three are worth defending out loud:

1. CHUNK BY SECTION, NOT BY CHARACTER COUNT.
   A postmortem has natural semantic boundaries: summary, timeline, root
   cause, resolution, follow-ups. Splitting every 500 characters would cut a
   root cause in half and staple the back of it to the front of a timeline.
   Every chunk here is one section of one document, so every chunk is about
   exactly one thing.

2. EVERY CHUNK CARRIES ITS PARENT'S METADATA.
   incident_id, service and severity ride along with each chunk. That means a
   retrieved chunk can always be traced back to a row in the incidents table,
   and it means retrieval can be filtered by service rather than relying on
   the embedding to somehow encode which service a paragraph is about.

3. THE HEADING IS PREPENDED TO THE CHUNK TEXT.
   A chunk that reads "Pool size raised from 20 to 40 per pod" is ambiguous on
   its own. The same chunk prefixed with "Root cause (INC-0020, payments)"
   embeds far closer to a question about why payments was slow. Cheap to do,
   noticeably better retrieval.

Embeddings are computed locally by the default model Chroma ships with. No
document content leaves the machine. For a demo that is convenience; in an
enterprise setting where the documents are the sensitive asset, it is a
governance decision.
"""

import re
from pathlib import Path

import chromadb

ROOT = Path(__file__).resolve().parent.parent
POSTMORTEM_DIR = ROOT / "data" / "postmortems"
CHROMA_DIR = ROOT / "data" / "chroma"
COLLECTION = "postmortems"

# Sections we do not index. Follow-up checklists are mostly boilerplate
# ("[ ] not done") and they dilute retrieval without adding meaning.
SKIP_SECTIONS = {"follow-ups"}


def parse_frontmatter(text):
    """Pull the bullet metadata block at the top of each postmortem."""
    meta = {}
    for line in text.splitlines():
        m = re.match(r"^-\s+\*\*(.+?):\*\*\s+(.+)$", line.strip())
        if m:
            key = m.group(1).strip().lower().replace(" ", "_")
            meta[key] = m.group(2).strip()
        if line.startswith("## "):
            break
    return meta


def split_sections(text):
    """Split on level-2 markdown headings. Returns (heading, body) pairs."""
    parts = re.split(r"^## +(.+)$", text, flags=re.MULTILINE)
    # parts[0] is everything before the first heading (title + metadata).
    sections = []
    for i in range(1, len(parts), 2):
        heading = parts[i].strip()
        body = parts[i + 1].strip()
        if body:
            sections.append((heading, body))
    return sections


def build_chunks():
    chunks = []
    files = sorted(POSTMORTEM_DIR.glob("*.md"))
    if not files:
        raise SystemExit(f"No postmortems found in {POSTMORTEM_DIR}")

    for path in files:
        text = path.read_text(encoding="utf-8")
        meta = parse_frontmatter(text)
        incident_id = meta.get("incident", path.stem.split("-md")[0])
        service = meta.get("service", "unknown")
        severity = meta.get("severity", "unknown")
        date = meta.get("date", "")
        title_match = re.search(r"^#\s+Postmortem:\s*(.+)$", text, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else path.stem

        for heading, body in split_sections(text):
            if heading.strip().lower() in SKIP_SECTIONS:
                continue

            # Decision 3: give the chunk its context in its own text.
            contextual_text = (
                f"{heading} for {incident_id} ({service}, {severity}, {date}): "
                f"{title}\n\n{body}"
            )

            chunks.append({
                "id": f"{incident_id}::{heading.lower().replace(' ', '_')}",
                "text": contextual_text,
                "metadata": {
                    "incident_id": incident_id,
                    "service": service,
                    "severity": severity,
                    "date": date,
                    "section": heading,
                    "title": title,
                    "source_file": path.name,
                },
            })

    return chunks


def main():
    chunks = build_chunks()

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    # Rebuild from scratch every run so ingestion is reproducible.
    try:
        client.delete_collection(COLLECTION)
    except Exception:
        pass
    collection = client.create_collection(COLLECTION)

    collection.add(
        ids=[c["id"] for c in chunks],
        documents=[c["text"] for c in chunks],
        metadatas=[c["metadata"] for c in chunks],
    )

    print(f"Indexed {len(chunks)} chunks from "
          f"{len(set(c['metadata']['incident_id'] for c in chunks))} postmortems")
    print(f"Vector store: {CHROMA_DIR}")

    by_section = {}
    for c in chunks:
        by_section[c["metadata"]["section"]] = by_section.get(
            c["metadata"]["section"], 0) + 1
    print("Chunks per section type:",
          ", ".join(f"{k}={v}" for k, v in sorted(by_section.items())))


if __name__ == "__main__":
    main()
