import os
from pathlib import Path
from striprtf.striprtf import rtf_to_text
from docx import Document


def load_rtf(filepath: str) -> str:
    # Try cp1252 first (most RTF from Windows), fallback to latin-1
    for enc in ("cp1252", "latin-1", "utf-8"):
        try:
            with open(filepath, "r", encoding=enc) as f:
                raw = f.read()
            return rtf_to_text(raw).strip()
        except (UnicodeDecodeError, Exception):
            continue
    return ""


def load_docx(filepath: str) -> str:
    doc = Document(filepath)
    return "\n".join(
        p.text.strip() for p in doc.paragraphs if p.text.strip()
    )


def load_document(filepath: str) -> str:
    ext = Path(filepath).suffix.lower()
    if ext == ".rtf":
        return load_rtf(filepath)
    elif ext == ".docx":
        return load_docx(filepath)
    return ""


def _load_single_file(filepath: Path) -> dict:
    try:
        text = load_document(str(filepath))
        if not text or len(text) < 50:
            return None
        return {
            "text": text,
            "metadata": {
                "filename": filepath.name,
                "category": filepath.parent.name,
                "filepath": str(filepath),
            }
        }
    except Exception:
        return None


def load_all_documents(data_dir: str) -> list:
    data_path = Path(data_dir)

    if not data_path.exists():
        print(f"[Loader] Directory not found: {data_dir}")
        return []

    supported = {".rtf", ".docx"}
    all_files = [f for f in data_path.rglob("*") if f.suffix.lower() in supported]
    print(f"[Loader] Found {len(all_files)} files in {data_dir}")

    workers = min(os.cpu_count() or 4, 8)
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(_load_single_file, all_files))

    documents = [r for r in results if r is not None]
    print(f"[Loader] Loaded {len(documents)} documents successfully ({workers} parallel workers)")
    return documents
