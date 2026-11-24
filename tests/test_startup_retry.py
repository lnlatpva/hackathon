"""Проверки безопасного старта API при временной недоступности БД."""
from sqlalchemy.exc import OperationalError
from app import main


def test_database_startup_retries_transient_connection_failure(monkeypatch):
    real_create_all = main.Base.metadata.create_all
    attempts = []
    pauses = []

    def temporary_failure(engine):
        attempts.append(1)
        if len(attempts) == 1:
            raise OperationalError('connect', {}, RuntimeError('temporary database DNS failure'))
        return real_create_all(engine)

    monkeypatch.setattr(main.Base.metadata, 'create_all', temporary_failure)
    monkeypatch.setattr(main, 'sleep', lambda seconds: pauses.append(seconds))
    app = main.create_app(database_url='sqlite:///:memory:', secret='a' * 48, allow_setup=False)
    assert app
    assert len(attempts) == 2
    assert pauses == [2]


def test_database_startup_does_not_hide_other_errors(monkeypatch):
    def invalid_schema(_engine):
        raise ValueError('bad schema')

    monkeypatch.setattr(main.Base.metadata, 'create_all', invalid_schema)
    try:
        main.create_app(database_url='sqlite:///:memory:', secret='a' * 48, allow_setup=False)
        assert False, 'ValueError expected'
    except ValueError as exc:
        assert str(exc) == 'bad schema'