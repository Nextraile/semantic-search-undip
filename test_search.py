from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

import backend
from search_routes import router

# New: Faking the sentence-transformer output
class FakeVector:
    def tolist(self):
        return [0.1, 0.2]

# New: Faking the embedding model
class FakeModel:
    def encode(self, query):
        return FakeVector()

# New: Faking the ChromaDB collection
class FakeCollection:
    def __init__(self, raw):
        self.raw = raw

    def query(self, **kwargs):
        return self.raw

# New: Creating a test app and fake search state
@pytest.fixture
def search_client():
    app = FastAPI()
    app.include_router(router)

    app.state.model = FakeModel()
    app.state.collection = FakeCollection(
        {
            "metadatas": [[]],
            "distances": [[]],
        }
    )

    with TestClient(app) as client:
        yield client, app


def test_threshold_filtering(search_client):
    client, app = search_client
    app.state.collection = FakeCollection(
        {
            "metadatas": [[
                {
                    "title": "Good title",
                    "creators": "Author",
                    "description": "Description",
                    "url": "https://example.com/good",
                    "date": "2026",
                },
                {
                    "title": "Filtered title",
                    "creators": "Author",
                    "description": "Description",
                    "url": "https://example.com/filtered",
                    "date": "2026",
                },
            ]],
            "distances": [[0.2, 0.8]],
        }
    )

    response = client.post(
        "/search",
        json={"query": "malaria", "max_threshold": 0.5},
    )

    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["results"][0]["url"] == "https://example.com/good"


def test_no_matches(search_client):
    client, app = search_client
    app.state.collection = FakeCollection(
        {
            "metadatas": [[]],
            "distances": [[]],
        }
    )

    response = client.post("/search", json={"query": "malaria"})

    assert response.status_code == 200
    assert response.json()["count"] == 0
    assert response.json()["results"] == []


def test_malformed_metadata_is_skipped(search_client):
    client, app = search_client
    app.state.collection = FakeCollection(
        {
            "metadatas": [[
                {"title": "", "url": "https://example.com/bad"},
                {
                    "title": "Valid title",
                    "creators": "Author",
                    "description": "Description",
                    "url": "https://example.com/good",
                    "date": "2026",
                },
            ]],
            "distances": [[0.2, 0.3]],
        }
    )

    response = client.post("/search", json={"query": "malaria"})

    assert response.status_code == 200
    assert response.json()["count"] == 1


def test_whitespace_query_is_rejected(search_client):
    client, _ = search_client

    response = client.post("/search", json={"query": "   "})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_missing_collection_stops_startup(monkeypatch):
    class MissingCollectionError(Exception):
        pass

    class FakePersistentClient:
        def get_collection(self, name):
            raise MissingCollectionError()

    monkeypatch.setattr(
        backend.chromadb.errors,
        "NotFoundError",
        MissingCollectionError,
    )
    monkeypatch.setattr(
        backend.chromadb,
        "PersistentClient",
        lambda path: FakePersistentClient(),
    )

    app = FastAPI()

    with pytest.raises(RuntimeError, match="collection"):
        async with backend.lifespan(app):
            pass