import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url


_test_database_url: URL | None = None
_admin_engine = None
_test_schema: str | None = None
if not os.environ.get("ENKIP_TEST_DATABASE_URL"):
    collect_ignore_glob = [
        "integration/*.py",
        "unit/test_smoke.py",
    ]


def _isolated_url(url: URL, schema: str) -> URL:
    return url.set(
        query={
            **url.query,
            "options": f"-csearch_path={schema},public",
        }
    )


def pytest_sessionstart(session) -> None:
    del session
    global _test_database_url, _admin_engine, _test_schema

    raw_url = os.environ.get("ENKIP_TEST_DATABASE_URL")
    if not raw_url:
        return

    url = make_url(raw_url)
    if not url.database or not url.database.lower().endswith("_test"):
        raise pytest.UsageError(
            "ENKIP_TEST_DATABASE_URL must point to a dedicated database "
            "whose name ends in '_test'; refusing to run database tests"
        )

    _test_database_url = url
    _test_schema = f"enkip_test_{uuid4().hex}"
    _admin_engine = create_engine(url)

    with _admin_engine.begin() as connection:
        connection.execute(
            text(f'CREATE SCHEMA "{_test_schema}"')
        )
        connection.execute(
            text("CREATE EXTENSION IF NOT EXISTS vector")
        )

    os.environ["DATABASE_URL"] = str(
        _isolated_url(url, _test_schema)
    )

    from alembic import command
    from alembic.config import Config

    command.upgrade(Config("alembic.ini"), "head")


def pytest_sessionfinish(session, exitstatus) -> None:
    del session, exitstatus
    if _admin_engine is None or _test_schema is None:
        return

    from packages.domain.database import engine

    engine.dispose()
    with _admin_engine.begin() as connection:
        connection.execute(
            text(f'DROP SCHEMA "{_test_schema}" CASCADE')
        )
    _admin_engine.dispose()


def pytest_collection_modifyitems(items) -> None:
    if _test_database_url is not None:
        return

    skip_database = pytest.mark.skip(
        reason=(
            "set ENKIP_TEST_DATABASE_URL to an isolated PostgreSQL "
            "database whose name ends in '_test'"
        )
    )
    database_node_fragments = (
        "tests/integration/",
        "tests\\integration\\",
        "tests/unit/test_smoke.py",
        "tests\\unit\\test_smoke.py",
        "test_retrieval_cases_match_expected_documents_lexically",
    )

    for item in items:
        if any(fragment in item.nodeid for fragment in database_node_fragments):
            item.add_marker(skip_database)


@pytest.fixture
def migration_schema():
    if _test_database_url is None or _admin_engine is None:
        pytest.skip(
            "set ENKIP_TEST_DATABASE_URL to run PostgreSQL migration tests"
        )

    schema = f"enkip_migration_test_{uuid4().hex}"
    schema_url = _isolated_url(_test_database_url, schema)
    with _admin_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))

    from alembic import command
    from alembic.config import Config
    from apps.api.config import settings

    original_database_url = settings.database_url
    settings.database_url = str(schema_url)
    try:
        command.upgrade(Config("alembic.ini"), "a8fd8271c5d9")
        yield schema_url
    finally:
        settings.database_url = original_database_url
        migration_engine = create_engine(schema_url)
        migration_engine.dispose()
        with _admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
