"""ai_usage.cached_input_tokens: how many input tokens OpenAI served from its prompt cache.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-27

Existing rows get 0 (they were logged before cached tokens were recorded).
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE ai_usage ADD COLUMN cached_input_tokens INTEGER NOT NULL DEFAULT 0")


def downgrade() -> None:
    op.execute("ALTER TABLE ai_usage DROP COLUMN cached_input_tokens")
