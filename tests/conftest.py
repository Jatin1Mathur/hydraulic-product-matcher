from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from hpm import service
from hpm.db import init_db, make_engine, make_session_factory
from hpm.embeddings import HashingEmbedder
from hpm.extract import RegexExtractor

ROOT = Path(__file__).resolve().parents[1]
DATASHEETS = ROOT / "data" / "datasheets"


@pytest.fixture(scope="session", autouse=True)
def datasheets() -> Path:
    """Generate the demo PDFs once if they are missing."""
    if not any(DATASHEETS.rglob("*.pdf")):
        subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_datasheets.py")], check=True)
    return DATASHEETS


def pytest_collection_modifyitems(config, items):
    if os.environ.get("DATABASE_URL"):
        return
    skip = pytest.mark.skip(reason="set DATABASE_URL to a PostgreSQL with pgvector to run")
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def Session(datasheets):  # noqa: N802
    """Fresh database with all demo datasheets ingested (needs DATABASE_URL)."""
    engine = make_engine()
    init_db(engine, reset=True)
    S = make_session_factory(engine)
    with S.begin() as s:
        results = service.ingest_folder(s, datasheets, HashingEmbedder(384), RegexExtractor())
    assert all(r.status == "ingested" for r in results), results
    return S
