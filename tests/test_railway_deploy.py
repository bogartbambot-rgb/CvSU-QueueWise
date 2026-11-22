"""Deployment configuration: Railway volume path support without breaking local SQLite."""
import sqlite3
from app import create_app


def test_database_path_can_be_set_by_environment(monkeypatch, tmp_path):
    database = tmp_path / 'persistent' / 'queuewise.db'
    monkeypatch.setenv('QUEUEWISE_DB_PATH', str(database))
    monkeypatch.setenv('QUEUEWISE_SECRET_KEY', 'test-secret-only-not-for-production')
    monkeypatch.setenv('QUEUEWISE_ADMIN_PASSWORD', 'strong-temp-value!2026')
    app = create_app()
    assert app.state.db_path == str(database)
    assert database.is_file()
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT username FROM users WHERE username='admin'").fetchone()[0] == 'admin'


def test_explicit_db_path_overrides_environment(monkeypatch, tmp_path):
    monkeypatch.setenv('QUEUEWISE_DB_PATH', str(tmp_path / 'ignore.db'))
    monkeypatch.setenv('QUEUEWISE_SECRET_KEY', 'test-secret-only-not-for-production')
    explicit = tmp_path / 'explicit' / 'db.sqlite3'
    app = create_app(db_path=str(explicit), testing=True)
    assert app.state.db_path == str(explicit)
    assert explicit.is_file()
    assert not (tmp_path / 'ignore.db').exists()
