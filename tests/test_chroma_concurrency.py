import threading
import time

from api.services import query_chromadb as chroma_service


class _FakeCollection:
    metadata = {"hnsw:space": "cosine"}

    def __init__(self, error=None):
        self.error = error

    def query(self, **_kwargs):
        if self.error:
            raise self.error
        return {
            "documents": [["A relevant answer"]],
            "metadatas": [[{"title": "Source"}]],
            "distances": [[0.1]],
        }


class _FakeClient:
    def __init__(self, collection):
        self.collection = collection

    def get_collection(self, name):
        assert name == "nutrifaq-collection"
        return self.collection


def test_query_reopens_chroma_after_missing_segment(monkeypatch):
    stale_collection = _FakeCollection(
        FileNotFoundError(
            2,
            "No such file or directory",
            "/db/chroma_db/old-segment/data_level0.bin",
        )
    )
    fresh_collection = _FakeCollection()
    clients = iter([_FakeClient(stale_collection), _FakeClient(fresh_collection)])
    client_calls = 0

    def fake_local_client(*_args, **_kwargs):
        nonlocal client_calls
        client_calls += 1
        return next(clients)

    monkeypatch.setattr(chroma_service, "_local_chroma_client", fake_local_client)
    chroma_service.release_local_chroma_handles()

    result = chroma_service.query_chromadb(
        "nutrifaq",
        data={"query_embedding": [0.1], "n_results": 1},
    )

    assert result["documents"] == [["A relevant answer"]]
    assert result["_distance_metric"] == "cosine"
    assert client_calls == 2


def test_chroma_access_guard_serializes_reads_and_mutations():
    mutation_started = threading.Event()
    allow_mutation_to_finish = threading.Event()
    reader_entered = threading.Event()

    def mutate():
        with chroma_service.chroma_access_guard():
            mutation_started.set()
            allow_mutation_to_finish.wait(timeout=1)

    def read():
        with chroma_service.chroma_access_guard():
            reader_entered.set()

    mutation_thread = threading.Thread(target=mutate)
    reader_thread = threading.Thread(target=read)
    mutation_thread.start()
    assert mutation_started.wait(timeout=1)
    reader_thread.start()

    time.sleep(0.05)
    assert reader_entered.is_set() is False

    allow_mutation_to_finish.set()
    mutation_thread.join(timeout=1)
    reader_thread.join(timeout=1)
    assert reader_entered.is_set() is True
