from contextlib import asynccontextmanager

import chromadb
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# New: Importing the search routes
from search_routes import (
    LLMError,
    SUMMARY_TOP_K,
    build_prompt,
    router as search_router,
    summarize_with_llm,
)

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DB_PATH = "./eprints_vector_db"
COLLECTION_NAME = "undip_research_search"

__all__ = [
    "LLMError",
    "SUMMARY_TOP_K",
    "app",
    "build_prompt",
    "lifespan",
]

# Change: Making it so now it validate startup failures
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Change: Connecting to the existing database
    client = chromadb.PersistentClient(path=DB_PATH)

    # Change: Cleaning up its lifespan state
    try:
        try:
            app.state.collection = client.get_collection(name=COLLECTION_NAME)
        except chromadb.errors.NotFoundError as exc:
            raise RuntimeError(
                f"ChromaDB collection '{COLLECTION_NAME}' was not found "
                f"in '{DB_PATH}'. Check the database path and make sure "
                "you've run the data-ingestion step."
            ) from exc

        from sentence_transformers import SentenceTransformer

        # Change: Loading the model at startup
        app.state.model = SentenceTransformer(MODEL_NAME)
        app.state.summarize = summarize_with_llm
        app.state.search_request_count = 0
        yield
    finally:
        app.state.model = None
        app.state.collection = None


app = FastAPI(
    title="Undip Research Semantic Search API",
    description="Semantic search over the harvested Undip eprints repository.",
    version="1.1.0",
    lifespan=lifespan,
)
# New: Registering the search routes
app.include_router(search_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
