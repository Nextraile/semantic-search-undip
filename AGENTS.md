# AGENTS.md

## What this repo is

One small service: FastAPI semantic search over harvested Universitas Diponegoro (Undip) eprints. Flat layout, pytest tests, no CI, no lockfile. Python 3.11.

- `backend.py` — served API: async search endpoint, embedding/query/summary offloaded via `run_in_threadpool`, explicit `RuntimeError` at startup when the Chroma collection is missing.
- `search_routes.py` and `search_schemas.py` — search routes, response/request models, and LLM fallback flow used by `backend.py`.
- `backend_example.py` — original sync version, not used by the Dockerfile.
- `data_harvesting.ipynb` — the only data ingestion path. Not run by the app, not in the Docker image (`.dockerignore` excludes `*.ipynb`).

## Data prerequisites (the #1 startup failure)

- `./eprints_vector_db` is gitignored and required at startup. If absent, the app fails to boot (`RuntimeError` in `backend.py`, `chromadb.errors.NotFoundError` in `backend_example.py`).
- Ingest by running the notebook top to bottom: harvest OAI-PMH (`https://v.undip.ac.id/cgi/oai2`, `metadataPrefix=oai_dc`, target 1000 valid records) → writes `eprints_undip_clean.json` → embeds `"{title}. {description}"` and inserts into Chroma.
- The notebook **deletes and recreates** collection `undip_research_search` with `{"hnsw:space": "cosine"}`. Re-running wipes existing vectors; there is no incremental update path.
- Inserts are batched at 1000 because Chroma rejects larger batches (~5461 cap).
- Notebook needs `sickle`, which is **not** in `requirements.txt` (installed via `%pip install` cell). Notebook also calls `%pip install sentence-transformers chromadb`.
- Embedding model (`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`) downloads at startup. Docker sets `HF_HOME=/model-cache` backed by the named `model_cache` volume so restarts don't re-download; local runs use the default HF cache.
- Ingestion and the app must use the same model, or stored vectors won't match query vectors.

## Commands

```bash
pip install -r requirements.txt
uvicorn backend:app --reload --port 8000   # local dev; run from repo root
docker compose up --build                  # serves backend.py on :8000
```

- Run uvicorn from the repo root: `DB_PATH = "./eprints_vector_db"` is relative to the CWD.
- Focused API tests: `python -m pytest -q test.py test_search.py` (install `requirements-dev.txt` first if needed). No linter, formatter, or typechecker is configured.
- `requirements.txt` is range-pinned (`chromadb>=1.5,<2`, `sentence-transformers>=6,<7`); code depends on Chroma 1.x APIs. `docker-compose.yml` bind-mounts `./eprints_vector_db`, so the host DB is what the container reads.

## API contract

- `POST /search` accepts `{query: str, max_threshold: float = 0.5}`. The query is stripped and must not be empty; threshold is between 0 and 2.
- Response wrapper includes `{query, max_threshold, count, results, status, ringkasan, arahan}`. `status` is `full`, `list_only`, or `no_results`; each result has **Indonesian keys**: `peringkat`, `skor`, `judul`, `penulis`, `deskripsi`, `url`, `date`.
- `skor` is a cosine **distance** (0 = identical), not a similarity, despite the name. Rows with `distance > max_threshold` are dropped and `peringkat` is a dense rank computed after filtering. Invalid metadata and duplicate URLs are skipped.
- Always fetches `N_RESULTS = 100` then filters in Python. The top `SUMMARY_TOP_K = 5` results are passed to the summary function. The default LLM function raises `LLMError`, returning `list_only`; no matches return `no_results` with `arahan`.
- `GET /health` reports the collection document count; `GET /metrics` reports search request count and last-search latency. There is no pagination or `offset`.
- Metadata shape is owned by the ingestion notebook; change both together.
