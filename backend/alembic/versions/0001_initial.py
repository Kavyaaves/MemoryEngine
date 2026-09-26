"""Initial schema: the canonical memory model, knowledge graph, lexicon and usage tables.

Revision ID: 0001
Revises:
Create Date: 2026-09-24

The schema is written out as SQL (generated once from the models) so this migration never
changes: later model changes need a new migration (`alembic revision --autogenerate`).
"""

from alembic import op
from sqlalchemy import text

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# pgvector (semantic search) and pg_trgm (fuzzy matching). Supabase keeps extensions in the
# "extensions" schema, which is on every connection's search_path; plain PostgreSQL has no
# such schema, so there they go into the default schema.
EXTENSIONS = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'extensions') THEN
        CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;
        CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA extensions;
    ELSE
        CREATE EXTENSION IF NOT EXISTS vector;
        CREATE EXTENSION IF NOT EXISTS pg_trgm;
    END IF;
END
$$;
"""

SCHEMA = [
    """
    CREATE TABLE ai_usage (
        id UUID NOT NULL,
        user_id UUID,
        provider VARCHAR(32) NOT NULL,
        model VARCHAR(100) NOT NULL,
        task VARCHAR(32) NOT NULL,
        day DATE NOT NULL,
        input_tokens INTEGER NOT NULL,
        output_tokens INTEGER NOT NULL,
        latency_ms INTEGER NOT NULL,
        success BOOLEAN NOT NULL,
        error TEXT,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id)
    )
    """,
    """
    CREATE INDEX ix_ai_usage_day ON ai_usage (day, provider)
    """,
    """
    CREATE INDEX ix_ai_usage_user_id ON ai_usage (user_id)
    """,
    """
    CREATE TABLE audit_log (
        id UUID NOT NULL,
        user_id UUID,
        action VARCHAR(64) NOT NULL,
        target VARCHAR(300),
        detail JSONB NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id)
    )
    """,
    """
    CREATE INDEX ix_audit_log_user_id ON audit_log (user_id)
    """,
    """
    CREATE TABLE users (
        id UUID NOT NULL,
        email VARCHAR(320) NOT NULL,
        password_hash VARCHAR(200) NOT NULL,
        display_name VARCHAR(200),
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        UNIQUE (email)
    )
    """,
    """
    CREATE TABLE events (
        id UUID NOT NULL,
        user_id UUID NOT NULL,
        title VARCHAR(500) NOT NULL,
        occasion_type VARCHAR(64) NOT NULL,
        start_at TIMESTAMP WITH TIME ZONE,
        end_at TIMESTAMP WITH TIME ZONE,
        confidence FLOAT NOT NULL,
        supporting_memory_ids JSONB NOT NULL,
        created_by VARCHAR(64) NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
    )
    """,
    """
    CREATE INDEX ix_events_user_id ON events (user_id)
    """,
    """
    CREATE TABLE lexicon_entries (
        id UUID NOT NULL,
        user_id UUID,
        surface_form VARCHAR(200) NOT NULL,
        canonical_form VARCHAR(200) NOT NULL,
        language VARCHAR(16) NOT NULL,
        gloss VARCHAR(300),
        frequency INTEGER NOT NULL,
        confidence FLOAT NOT NULL,
        source VARCHAR(32) NOT NULL,
        user_verified BOOLEAN NOT NULL,
        PRIMARY KEY (id),
        UNIQUE NULLS NOT DISTINCT (user_id, surface_form, canonical_form),
        FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
    )
    """,
    """
    CREATE INDEX ix_lexicon_entries_canonical_form ON lexicon_entries (canonical_form)
    """,
    """
    CREATE INDEX ix_lexicon_entries_surface_form ON lexicon_entries (surface_form)
    """,
    """
    CREATE INDEX ix_lexicon_entries_user_id ON lexicon_entries (user_id)
    """,
    """
    CREATE TABLE people (
        id UUID NOT NULL,
        user_id UUID NOT NULL,
        display_name VARCHAR(300) NOT NULL,
        is_self BOOLEAN NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
    )
    """,
    """
    CREATE INDEX ix_people_user_id ON people (user_id)
    """,
    """
    CREATE TABLE places (
        id UUID NOT NULL,
        user_id UUID NOT NULL,
        name VARCHAR(300) NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        UNIQUE (user_id, name),
        FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
    )
    """,
    """
    CREATE INDEX ix_places_user_id ON places (user_id)
    """,
    """
    CREATE TABLE sources (
        id UUID NOT NULL,
        user_id UUID NOT NULL,
        source_type VARCHAR(32) NOT NULL,
        name VARCHAR(500) NOT NULL,
        fingerprint VARCHAR(128) NOT NULL,
        meta JSONB NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        last_processed_at TIMESTAMP WITH TIME ZONE,
        PRIMARY KEY (id),
        UNIQUE (user_id, source_type, fingerprint),
        FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
    )
    """,
    """
    CREATE INDEX ix_sources_user_id ON sources (user_id)
    """,
    """
    CREATE TABLE conversations (
        id UUID NOT NULL,
        user_id UUID NOT NULL,
        source_id UUID NOT NULL,
        title VARCHAR(500) NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
        FOREIGN KEY(source_id) REFERENCES sources (id) ON DELETE CASCADE
    )
    """,
    """
    CREATE INDEX ix_conversations_user_id ON conversations (user_id)
    """,
    """
    CREATE TABLE ingestion_jobs (
        id UUID NOT NULL,
        user_id UUID NOT NULL,
        source_id UUID,
        filename VARCHAR(1000) NOT NULL,
        source_type VARCHAR(32) NOT NULL,
        object_key VARCHAR(1000) NOT NULL,
        file_hash VARCHAR(64) NOT NULL,
        mime_type VARCHAR(200),
        options JSONB NOT NULL,
        status VARCHAR(16) NOT NULL,
        progress FLOAT NOT NULL,
        stats JSONB NOT NULL,
        error TEXT,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
        FOREIGN KEY(source_id) REFERENCES sources (id) ON DELETE SET NULL
    )
    """,
    """
    CREATE INDEX ix_ingestion_jobs_file_hash ON ingestion_jobs (file_hash)
    """,
    """
    CREATE INDEX ix_ingestion_jobs_user_id ON ingestion_jobs (user_id)
    """,
    """
    CREATE TABLE person_aliases (
        id UUID NOT NULL,
        user_id UUID NOT NULL,
        person_id UUID NOT NULL,
        alias VARCHAR(300) NOT NULL,
        normalized_alias VARCHAR(300) NOT NULL,
        status VARCHAR(16) NOT NULL,
        confidence FLOAT NOT NULL,
        PRIMARY KEY (id),
        UNIQUE (user_id, alias, person_id),
        FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
        FOREIGN KEY(person_id) REFERENCES people (id) ON DELETE CASCADE
    )
    """,
    """
    CREATE INDEX ix_person_aliases_normalized_alias ON person_aliases (normalized_alias)
    """,
    """
    CREATE INDEX ix_person_aliases_user_id ON person_aliases (user_id)
    """,
    """
    CREATE TABLE memories (
        id UUID NOT NULL,
        user_id UUID NOT NULL,
        source_id UUID NOT NULL,
        conversation_id UUID,
        source_type VARCHAR(32) NOT NULL,
        source_record_id VARCHAR(200),
        content_hash VARCHAR(64) NOT NULL,
        timestamp TIMESTAMP WITH TIME ZONE,
        author_raw VARCHAR(300),
        author_person_id UUID,
        text TEXT NOT NULL,
        normalized_text TEXT NOT NULL,
        transliteration TEXT,
        gloss TEXT,
        language VARCHAR(16) NOT NULL,
        script VARCHAR(16) NOT NULL,
        search_text TEXT NOT NULL,
        search_tsv TSVECTOR GENERATED ALWAYS AS (to_tsvector('simple', coalesce(search_text, ''))) STORED,
        embedding VECTOR(768),
        embedding_model VARCHAR(100),
        processing_version INTEGER NOT NULL,
        meta JSONB NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        UNIQUE (user_id, content_hash),
        FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
        FOREIGN KEY(source_id) REFERENCES sources (id) ON DELETE CASCADE,
        FOREIGN KEY(conversation_id) REFERENCES conversations (id) ON DELETE CASCADE,
        FOREIGN KEY(author_person_id) REFERENCES people (id) ON DELETE SET NULL
    )
    """,
    """
    CREATE INDEX ix_memories_author_person_id ON memories (author_person_id)
    """,
    """
    CREATE INDEX ix_memories_conversation_id ON memories (conversation_id)
    """,
    """
    CREATE INDEX ix_memories_embedding_hnsw ON memories USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)
    """,
    """
    CREATE INDEX ix_memories_search_trgm ON memories USING gin (search_text gin_trgm_ops)
    """,
    """
    CREATE INDEX ix_memories_search_tsv ON memories USING gin (search_tsv)
    """,
    """
    CREATE INDEX ix_memories_source_id ON memories (source_id)
    """,
    """
    CREATE INDEX ix_memories_user_id ON memories (user_id)
    """,
    """
    CREATE INDEX ix_memories_user_ts ON memories (user_id, timestamp)
    """,
    """
    CREATE TABLE media_assets (
        id UUID NOT NULL,
        user_id UUID NOT NULL,
        source_id UUID NOT NULL,
        memory_id UUID,
        kind VARCHAR(16) NOT NULL,
        object_key VARCHAR(1000) NOT NULL,
        mime_type VARCHAR(200),
        size_bytes INTEGER NOT NULL,
        sha256 VARCHAR(64) NOT NULL,
        meta JSONB NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
        FOREIGN KEY(source_id) REFERENCES sources (id) ON DELETE CASCADE,
        FOREIGN KEY(memory_id) REFERENCES memories (id) ON DELETE CASCADE
    )
    """,
    """
    CREATE INDEX ix_media_assets_memory_id ON media_assets (memory_id)
    """,
    """
    CREATE INDEX ix_media_assets_user_id ON media_assets (user_id)
    """,
    """
    CREATE TABLE memory_participants (
        memory_id UUID NOT NULL,
        person_id UUID NOT NULL,
        role VARCHAR(16) NOT NULL,
        PRIMARY KEY (memory_id, person_id, role),
        FOREIGN KEY(memory_id) REFERENCES memories (id) ON DELETE CASCADE,
        FOREIGN KEY(person_id) REFERENCES people (id) ON DELETE CASCADE
    )
    """,
    """
    CREATE INDEX ix_memory_participants_person_id ON memory_participants (person_id)
    """,
    """
    CREATE TABLE relationships (
        id UUID NOT NULL,
        user_id UUID NOT NULL,
        src_type VARCHAR(32) NOT NULL,
        src_id UUID NOT NULL,
        rel_type VARCHAR(32) NOT NULL,
        dst_type VARCHAR(32) NOT NULL,
        dst_id UUID NOT NULL,
        weight FLOAT NOT NULL,
        confidence FLOAT NOT NULL,
        source_memory_id UUID,
        created_by VARCHAR(64) NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        UNIQUE NULLS NOT DISTINCT (user_id, src_type, src_id, rel_type, dst_type, dst_id, source_memory_id),
        FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
        FOREIGN KEY(source_memory_id) REFERENCES memories (id) ON DELETE CASCADE
    )
    """,
    """
    CREATE INDEX ix_rel_dst ON relationships (user_id, dst_type, dst_id)
    """,
    """
    CREATE INDEX ix_rel_src ON relationships (user_id, src_type, src_id)
    """,
    """
    CREATE INDEX ix_relationships_user_id ON relationships (user_id)
    """,
]

DROP_TABLES = [
    "DROP TABLE IF EXISTS relationships CASCADE",
    "DROP TABLE IF EXISTS memory_participants CASCADE",
    "DROP TABLE IF EXISTS media_assets CASCADE",
    "DROP TABLE IF EXISTS memories CASCADE",
    "DROP TABLE IF EXISTS person_aliases CASCADE",
    "DROP TABLE IF EXISTS ingestion_jobs CASCADE",
    "DROP TABLE IF EXISTS conversations CASCADE",
    "DROP TABLE IF EXISTS sources CASCADE",
    "DROP TABLE IF EXISTS places CASCADE",
    "DROP TABLE IF EXISTS people CASCADE",
    "DROP TABLE IF EXISTS lexicon_entries CASCADE",
    "DROP TABLE IF EXISTS events CASCADE",
    "DROP TABLE IF EXISTS users CASCADE",
    "DROP TABLE IF EXISTS audit_log CASCADE",
    "DROP TABLE IF EXISTS ai_usage CASCADE",
]


def enable_row_level_security_everywhere() -> None:
    """Supabase publishes every table in the `public` schema through its automatic REST API.
    Turning on row-level security with no policies makes those tables unreadable there,
    while this backend (which connects as the tables' owner) is unaffected. On plain
    PostgreSQL this is harmless."""
    op.execute("""
    DO $$
    DECLARE table_name text;
    BEGIN
        FOR table_name IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
            EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', table_name);
        END LOOP;
    END
    $$;
    """)


def upgrade() -> None:
    op.execute(EXTENSIONS)
    for statement in SCHEMA:
        op.execute(statement)
    enable_row_level_security_everywhere()  # includes alembic's own alembic_version table

    # The built-in Tanglish word list (user_id NULL = shared by everyone).
    from app.multilingual.personal_lexicon import seed_rows

    op.get_bind().execute(text(
        "INSERT INTO lexicon_entries (id, user_id, surface_form, canonical_form, language, gloss, frequency, "
        "confidence, source, user_verified) VALUES (gen_random_uuid(), NULL, :surface_form, :canonical_form, "
        ":language, :gloss, 0, :confidence, :source, :user_verified) ON CONFLICT DO NOTHING"), seed_rows())


def downgrade() -> None:
    for statement in DROP_TABLES:
        op.execute(statement)
