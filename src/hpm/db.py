"""PostgreSQL schema (SQLAlchemy 2.0 + pgvector).

manufacturers 1--n documents 1--n chunks        (text + embedding + full-text index, for RAG)
manufacturers 1--n products  1--n spec_sources  (where each value came from: page, raw text, method)

Products keep typed, canonical-unit columns so engineering rules can filter in SQL.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    text,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from hpm.config import settings

DIM = settings.embed_dim


class Base(DeclarativeBase):
    pass


class Manufacturer(Base):
    __tablename__ = "manufacturers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    is_reference: Mapped[bool] = mapped_column(Boolean, default=False)  # True = our own portfolio


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    manufacturer_id: Mapped[int] = mapped_column(ForeignKey("manufacturers.id"))
    filename: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    n_pages: Mapped[int] = mapped_column(Integer)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    manufacturer: Mapped[Manufacturer] = relationship()
    chunks: Mapped[list[Chunk]] = relationship(back_populates="document", cascade="all, delete-orphan")


class Chunk(Base):
    __tablename__ = "chunks"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    page: Mapped[int] = mapped_column(Integer)
    chunk_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    embedding = mapped_column(Vector(DIM))
    tsv = mapped_column(TSVECTOR, Computed("to_tsvector('english', text)", persisted=True))
    document: Mapped[Document] = relationship(back_populates="chunks")

    __table_args__ = (
        Index("chunks_tsv_gin", "tsv", postgresql_using="gin"),
        Index(
            "chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    manufacturer_id: Mapped[int] = mapped_column(ForeignKey("manufacturers.id"))
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    model: Mapped[str] = mapped_column(String(100))
    component_type: Mapped[str] = mapped_column(String(40), index=True)
    circuit: Mapped[str | None] = mapped_column(String(10))
    mounting: Mapped[str | None] = mapped_column(String(20))
    nominal_size: Mapped[str | None] = mapped_column(String(10))
    displacement: Mapped[float | None] = mapped_column(Float)  # cm3/rev
    max_pressure: Mapped[float | None] = mapped_column(Float)  # bar
    cont_pressure: Mapped[float | None] = mapped_column(Float)  # bar
    max_speed: Mapped[float | None] = mapped_column(Float)  # rpm
    max_flow: Mapped[float | None] = mapped_column(Float)  # L/min
    weight: Mapped[float | None] = mapped_column(Float)  # kg
    control_text: Mapped[str | None] = mapped_column(Text)
    embedding = mapped_column(Vector(DIM))  # embedding of the profile text
    manufacturer: Mapped[Manufacturer] = relationship()
    document: Mapped[Document | None] = relationship()
    sources: Mapped[list[SpecSource]] = relationship(cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("manufacturer_id", "model"),)


class SpecSource(Base):
    __tablename__ = "spec_sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    attribute: Mapped[str] = mapped_column(String(40))
    raw: Mapped[str] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(String(10))
    verified: Mapped[bool] = mapped_column(Boolean, default=True)


def make_engine(url: str | None = None) -> Engine:
    return create_engine(url or settings.database_url, pool_pre_ping=True)


def make_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(engine, expire_on_commit=False)


def init_db(engine: Engine, reset: bool = False) -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    if reset:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
