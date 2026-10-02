# LexSetu

**Bridge to Justice** | AI-powered legal assistant for advocates and legal interns

---

## What is LexSetu?

LexSetu is a free, open-source legal AI platform built for Indian legal professionals. It helps advocates and interns:

- **Find real cases** — Search actual Indian court judgments with proper citations
- **Draft documents** — Generate error-free legal drafts from a library of 1841 templates
- **Get legal guidance** — Article-backed Q&A for common legal questions

No hallucinations. No guesswork. Every answer is grounded in real legal data.

---

## Features

| Feature | Description |
|---|---|
| Case Finder | RAG-powered search over Indian Kanoon judgments |
| Draft Assistant | Generate contracts, petitions, plaints from templates |
| Legal Aid | Article-backed Q&A for legal guidance |
| Offline Mode | Full functionality via Ollama — no internet needed |

---

## User Flow

```mermaid
flowchart LR
    Visitor(["Visitor"]) --> Login["/login<br/>Register or sign in"]
    Login -->|"JWT issued"| Shell["AppShell<br/>persistent sidebar nav"]

    Shell --> Home["/ — Dashboard"]
    Shell --> VerifyFiling["/verify-filing<br/>Flagship: Citation Integrity Check"]
    Shell --> CaseFinder["/case-finder<br/>RAG search over judgments"]
    Shell --> DraftAssistant["/draft-assistant<br/>Generate grounded drafts"]
    Shell --> ClauseConflict["/clause-conflict<br/>Contract analysis"]
    Shell --> Statutes["/statutes<br/>Bare Acts and India Code"]
    Shell --> LegalAid["/legal-aid<br/>Q&A chat"]

    DraftAssistant -->|"Inspect in Draft Review"| DraftReview["/draft-review<br/>2-pass structural and source review"]

    VerifyFiling --> Persona{"Persona selected"}
    Persona --> Lawyer["Lawyer view<br/>list, export emphasized"]
    Persona --> Paralegal["Paralegal view<br/>list, export emphasized"]
    Persona --> Student["Student view<br/>step-by-step walkthrough"]
    Persona --> Judge["Judge view<br/>list"]

    VerifyFiling -->|"Flag a wrong verdict"| Correction["Correction submitted"]
    Correction -->|"admin or advocate role"| AdminCorrections["/admin/corrections<br/>Review flagged corrections"]

    Shell -->|"toggle"| LocalMode{"Local-only mode?"}
    LocalMode -->|"On"| Offline["Ollama only<br/>citation verification disabled"]
    LocalMode -->|"Off"| Online["Groq, Indian Kanoon and India Code available"]
```

Every page under `AppShell` requires a valid session (`ProtectedRoute`); an expired or missing JWT redirects back to `/login`. The persona picked on Verify Filing (lawyer / paralegal / student / judge) only changes copy, default view and export emphasis — it never hides a result another persona would see. Local-only mode is a standing toggle in the sidebar, not a per-page setting: switching it on routes every LLM call to Ollama and disables cloud-only checks (citation verification requires Groq's entailment model and is blocked outright in this mode).

---

## Tech Stack

- **Backend** — Python, FastAPI
- **LLM (Online)** — Groq API (Llama 3.3 70B) — free tier
- **LLM (Offline)** — Ollama (Llama 3.2)
- **Embeddings** — sentence-transformers (local, free)
- **Vector DB** — Qdrant (local, embedded)
- **Case Data** — Indian Kanoon (live search + Hugging Face dataset)
- **Frontend** — React

---

## Architecture

```mermaid
flowchart TB
    subgraph Client["Frontend — React SPA (Vite)"]
        UI["Pages<br/>Verify Filing · Case Finder · Draft Assistant<br/>Draft Review · Clause Conflict · Statutes · Legal Aid · Admin"]
        Ctx["Context<br/>Auth · Persona · Local-only Mode · Language"]
    end

    subgraph API["Backend — FastAPI (backend/main.py)"]
        Auth["/auth"]
        Workflow["/workflow"]
        Compliance["/compliance"]
        Docs["/documents"]
        Cases["/cases"]
        LegalAidRoute["/legal-aid"]
        Review["/review"]
        Citations["/citations"]
        Statutes["/statutes"]
        Admin["/admin"]
        Translate["/translate"]
    end

    subgraph Services["Service Layer (backend/services)"]
        RAG["rag.py<br/>embeddings + Qdrant search"]
        LLM["llm.py<br/>Groq / Ollama router"]
        Verifier["citation_verifier.py<br/>10-stage citation pipeline"]
        Reasoning["fact_manifest.py + legal_reasoning_engine.py<br/>grounded drafting"]
        IndiaCode["india_code_grounding.py<br/>indiacode_client.py"]
        Scraper["scraper.py + external_case_lookup.py"]
        ReviewEngine["review_engine.py<br/>2-pass draft review"]
        ComplianceFetcher["compliance_fetcher.py"]
    end

    subgraph Data["Storage"]
        SQL[("Relational DB<br/>Users · QueryLog · Corrections<br/>Acts · Provisions · Workflows")]
        Qdrant[("Qdrant, embedded<br/>draft templates + judgment corpus")]
    end

    subgraph External["External Systems"]
        Groq["Groq API<br/>Llama 3.3 / gpt-oss-120b"]
        Ollama["Ollama, local<br/>offline fallback"]
        Kanoon["Indian Kanoon<br/>live scrape"]
        IndiaCodeGov["indiacode.nic.in<br/>canonical statute text"]
        HF["HuggingFace dataset<br/>judgment corpus ingest"]
    end

    Scheduler["APScheduler<br/>compliance refresh every 12h"]

    UI -->|"fetch /api/*"| API
    Ctx --> UI
    API --> Services
    Services --> SQL
    Services --> Qdrant
    LLM --> Groq
    LLM --> Ollama
    Scraper --> Kanoon
    IndiaCode --> IndiaCodeGov
    HF -.->|"ingest_judgments.py"| Qdrant
    Scheduler --> ComplianceFetcher
    ComplianceFetcher --> SQL
```

Every route module calls into the service layer rather than talking to Groq, Qdrant or an external site directly — `llm.py` is the single place that decides Groq vs. Ollama (`force_local` / the `X-Local-Only` header), and `rag.py` is the single place that talks to Qdrant. Citation Verification (`citations.py` → `citation_verifier.py`) is deliberately cloud-only: it's pinned to Groq's entailment model with no local fallback, so it fails fast in local-only mode instead of silently degrading the verification guarantee. A background APScheduler job refreshes compliance alerts every 12 hours independently of user traffic.

---

## Project Structure

```
nyayasetu/
├── backend/
│   ├── main.py              # FastAPI app entry point
│   ├── routes/              # API route handlers
│   ├── services/            # Core logic (RAG, LLM, scraper)
│   ├── models/              # Pydantic data models
│   └── utils/               # Helpers and loaders
├── frontend/
│   ├── src/
│   │   ├── pages/           # Case Finder, Draft Assistant, Legal Aid
│   │   └── components/      # Reusable UI components
├── data/
│   ├── drafts/              # Legal draft templates (RTF/DOCX)
│   ├── cases/               # Case study data
│   └── articles/            # Legal articles
└── README.md
```

---

## Getting Started

### Prerequisites
- Python 3.10+
- Node.js 18+
- Ollama (for offline mode)

### Backend Setup
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env      # Configure PostgreSQL, Qdrant, and Groq keys
alembic upgrade head      # Run database migrations
uvicorn main:app --reload
```

### Frontend Setup
```bash
cd frontend
npm install
npm run dev               # Development server at http://localhost:3000
# For production build:
# npm run build
```

### Offline Mode (Ollama)
```bash
ollama pull llama3.2
# Ollama runs automatically as fallback when Groq is unavailable
```

---

## Environment Variables

See `backend/.env.example` for full configuration details.

```env
DATABASE_URL=postgresql://user:password@host:port/dbname
QDRANT_URL=https://your-cluster.cloud.qdrant.io
QDRANT_API_KEY=your_qdrant_api_key
GROQ_API_KEY=your_groq_api_key
JWT_SECRET_KEY=your_jwt_secret_key
ENCRYPTION_KEY=your_fernet_encryption_key

---

## License

MIT License — free to use, modify, and distribute.

---

*Built for the people. Powered by open source.*
