from dotenv import load_dotenv
load_dotenv()

from services.judgment_search import ingest_judgments

if __name__ == "__main__":
    print("=" * 55)
    print("LexSetu — Judgment Corpus Ingestion Pipeline (S1)")
    print("=" * 55)
    print("This downloads judgment parquet file(s) from")
    print("vaquill/open-india-law (Hugging Face, gated — needs HF_TOKEN)")
    print("and embeds them into the 'judgments' Qdrant collection.")
    print("=" * 55)
    ingest_judgments()
    print("=" * 55)
    print("Done!")
    print("=" * 55)
