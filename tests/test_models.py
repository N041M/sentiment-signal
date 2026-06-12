"""Model-level tests against a real Postgres test database.

These exercise the pgvector/JSONB/UUID/ARRAY columns that cannot run on SQLite.
They skip automatically if PostgreSQL is unavailable (see conftest.py).
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from sentiment_signal.db.models import Person, Statement, StatementAnalysis


def _make_person(session, name="Test Person", aliases=("TP",), tier=2):
    p = Person(canonical_name=name, aliases=list(aliases), influence_tier=tier)
    session.add(p)
    session.flush()
    return p


def _make_statement(session, person, content_hash, text="hello world"):
    s = Statement(
        person_id=person.id,
        source_type="speech",
        raw_text=text,
        content_hash=content_hash,
        published_at=datetime(2024, 1, 1, tzinfo=UTC),
        influence_tier=person.influence_tier,
    )
    session.add(s)
    session.flush()
    return s


class TestPerson:
    def test_roundtrip_with_array_aliases(self, db_session):
        _make_person(db_session, name="Jane Doe", aliases=["Doe", "J. Doe"])
        got = db_session.scalar(select(Person).where(Person.canonical_name == "Jane Doe"))
        assert got is not None
        assert got.id is not None  # UUID default applied
        assert got.aliases == ["Doe", "J. Doe"]  # ARRAY(Text) round-trips

    def test_canonical_name_unique(self, db_session):
        _make_person(db_session, name="Dup")
        db_session.add(Person(canonical_name="Dup", influence_tier=1))
        with pytest.raises(IntegrityError):
            db_session.flush()


class TestStatement:
    def test_content_hash_unique(self, db_session):
        p = _make_person(db_session, name="Speaker A")
        _make_statement(db_session, p, content_hash="a" * 64)
        # Second statement with the same content_hash must violate the unique constraint
        dup = Statement(
            person_id=p.id,
            source_type="speech",
            raw_text="different text",
            content_hash="a" * 64,
            published_at=datetime(2024, 2, 1, tzinfo=UTC),
            influence_tier=1,
        )
        db_session.add(dup)
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_person_relationship(self, db_session):
        p = _make_person(db_session, name="Speaker B")
        s = _make_statement(db_session, p, content_hash="b" * 64)
        assert s.person.canonical_name == "Speaker B"


class TestStatementAnalysis:
    def test_vector_embedding_roundtrip(self, db_session):
        p = _make_person(db_session, name="Speaker C")
        s = _make_statement(db_session, p, content_hash="c" * 64)
        embedding = [0.01 * i for i in range(768)]
        sa = StatementAnalysis(
            statement_id=s.id,
            sentiment_score=0.42,
            sentiment_label="positive",
            embedding=embedding,
            emotion_vector={"joy": 0.8, "fear": 0.1},  # JSONB
        )
        db_session.add(sa)
        db_session.flush()

        got = db_session.scalar(
            select(StatementAnalysis).where(StatementAnalysis.statement_id == s.id)
        )
        assert got is not None
        assert len(list(got.embedding)) == 768  # Vector(768) round-trips
        assert got.emotion_vector["joy"] == 0.8  # JSONB round-trips
        assert got.sentiment_score == pytest.approx(0.42)

    def test_clustering_columns_exist(self, db_session):
        # Guards the migration: cluster_id / umap_x / umap_y must be writable
        p = _make_person(db_session, name="Speaker D")
        s = _make_statement(db_session, p, content_hash="d" * 64)
        sa = StatementAnalysis(
            statement_id=s.id,
            cluster_id=3,
            umap_x=1.5,
            umap_y=-2.0,
            topic_classification="inflation / rates",
        )
        db_session.add(sa)
        db_session.flush()
        got = db_session.scalar(
            select(StatementAnalysis).where(StatementAnalysis.statement_id == s.id)
        )
        assert got.cluster_id == 3
        assert got.umap_x == pytest.approx(1.5)
        assert got.topic_classification == "inflation / rates"
