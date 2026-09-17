import os


def test_get_postgres_dsn_includes_required_values(monkeypatch):
    monkeypatch.setenv("POSTGRES_HOST", "nutrifaq-bd-server.postgres.database.azure.com")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("POSTGRES_DB", "postgres")
    monkeypatch.setenv("POSTGRES_USER", "nutrifaqadmin")
    monkeypatch.setenv("POSTGRES_PASSWORD", "super-secret-password")

    from api.query_chromadb import get_postgres_dsn

    dsn = get_postgres_dsn()

    assert dsn.startswith("postgresql://")
    assert "nutrifaqadmin" in dsn
    assert "nutrifaq-bd-server.postgres.database.azure.com" in dsn
    assert "sslmode=require" in dsn
