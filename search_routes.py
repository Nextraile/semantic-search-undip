import time
import logging

# Refactor: Move the /search into search_routes.py for scalability
from fastapi import APIRouter, Request

# New: These are imports I added
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from search_schemas import SearchMetadata
from search_schemas import SearchRequest, SearchResponse, SearchResult

# New: Creating a router for search
router = APIRouter()
# New: Setting the maximum number of results
N_RESULTS = 100
SUMMARY_TOP_K = 5
GUIDANCE = [
    "Naikkan batas jarak (max_threshold) agar lebih longgar.",
    "Coba kata kunci lain.",
    "Perluas topik pencarian.",
]

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
)
log = logging.getLogger("aisen.search")


class LLMError(Exception):
    pass


def build_prompt(query: str, results: list[SearchResult]) -> str:
    sources = "\n\n".join(f"[{r.peringkat}] {r.judul}\n{r.deskripsi}" for r in results)
    return (
        "Jawab pertanyaan berdasarkan HANYA sumber di bawah ini. "
        "Setiap klaim wajib diberi sitasi berformat [n] sesuai nomor sumber. "
        "Jika sumber tidak cukup, katakan demikian.\n\n"
        f"Pertanyaan: {query}\n\nSumber:\n{sources}"
    )


def summarize_with_llm(query: str, results: list[SearchResult]) -> str:
    """Replace this stub with the team's LLM integration."""
    raise LLMError("LLM belum dikonfigurasi")


# Change: Making it to be async def + adding thread offloading
@router.post("/search", response_model=SearchResponse)
async def search(payload: SearchRequest, request: Request) -> SearchResponse:
    # New: Measuring search latency
    started_at = time.perf_counter()
    # Change: Getting the model and collection from app state
    model = request.app.state.model
    collection = request.app.state.collection

    # Change: Running blocking calls in a thread
    query_vector = await run_in_threadpool(model.encode, payload.query)
    query_vector = query_vector.tolist()

    raw = await run_in_threadpool(
        collection.query,
        query_embeddings=[query_vector],
        n_results=N_RESULTS,
        include=["metadatas", "distances"],
    )

    results: list[SearchResult] = []
    seen_urls: set[str] = set()
    rank = 0

    # Change: Filtering empty metadata and duplicate URLs
    for metadata, distance in zip(raw["metadatas"][0], raw["distances"][0]):
        if distance > payload.max_threshold:
            continue

        try:
            validated = SearchMetadata.model_validate(metadata)
        except ValidationError:
            continue

        url = validated.url.strip()

        if url in seen_urls:
            continue

        seen_urls.add(url)
        rank += 1

        results.append(
            SearchResult(
                peringkat=rank,
                skor=distance,
                judul=validated.title,
                penulis=validated.creators,
                deskripsi=validated.description,
                url=url,
                date=validated.date,
            )
        )

    ringkasan = None
    arahan: list[str] = []
    if not results:
        status = "no_results"
        arahan = list(GUIDANCE)
    else:
        summarize = getattr(request.app.state, "summarize", summarize_with_llm)
        try:
            ringkasan = await run_in_threadpool(
                summarize, payload.query, results[:SUMMARY_TOP_K]
            )
            status = "full"
        except Exception:
            log.exception("LLM gagal, fallback ke daftar jurnal saja")
            status = "list_only"

    elapsed_ms = (time.perf_counter() - started_at) * 1000
    app_state = request.app.state
    app_state.last_search_latency_ms = elapsed_ms
    app_state.search_request_count = getattr(app_state, "search_request_count", 0) + 1
    log.info(
        "search status=%s count=%d max_threshold=%.2f duration_ms=%.0f",
        status,
        len(results),
        payload.max_threshold,
        elapsed_ms,
    )

    return SearchResponse(
        query=payload.query,
        max_threshold=payload.max_threshold,
        count=len(results),
        results=results,
        status=status,
        ringkasan=ringkasan,
        arahan=arahan,
    )


# New: Adding a health endpoint
@router.get("/health")
def health(request: Request):
    # Change: Reading health state from the app
    return {"status": "ok", "documents": request.app.state.collection.count()}


# New: Adding a search metrics endpoint
@router.get("/metrics")
async def metrics(request: Request):
    app_state = request.app.state

    return {
        "search_request_count": getattr(app_state, "search_request_count", 0),
        "last_search_latency_ms": getattr(app_state, "last_search_latency_ms", None),
    }