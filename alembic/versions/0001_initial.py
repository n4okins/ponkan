"""initial normalized study schema

Revision ID: 0001
Revises:
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

UUID = sa.Uuid(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "learners",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "materials",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("category", sa.String(64), nullable=False, server_default="general"),
        sa.Column("default_prompt_lang", sa.String(32), nullable=False, server_default=""),
        sa.Column("default_answer_lang", sa.String(32), nullable=False, server_default=""),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "import_sources",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("material_id", UUID, sa.ForeignKey("materials.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False, server_default="Import"),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("config", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_synced_at", sa.DateTime(timezone=True)),
        sa.Column("last_sync_status", sa.String(32), nullable=False, server_default="never"),
        sa.Column("last_sync_error", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('google_sheets','csv_url')", name="ck_import_kind"),
    )
    op.create_table(
        "questions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("material_id", UUID, sa.ForeignKey("materials.id", ondelete="CASCADE"), nullable=False),
        sa.Column("import_source_id", UUID, sa.ForeignKey("import_sources.id", ondelete="SET NULL")),
        sa.Column("external_key", sa.String(255)),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False, server_default=""),
        sa.Column("question_type", sa.String(32), nullable=False, server_default="auto"),
        sa.Column("prompt_lang", sa.String(32), nullable=False, server_default=""),
        sa.Column("answer_lang", sa.String(32), nullable=False, server_default=""),
        sa.Column("content_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("metadata", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("import_source_id", "external_key", name="uq_question_external_key"),
        sa.CheckConstraint("question_type IN ('auto','card','multiple_choice')", name="ck_question_type"),
    )
    op.create_index(
        "ix_question_material_active",
        "questions",
        ["material_id", "archived_at", "is_enabled"],
    )
    op.create_table(
        "question_options",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("question_id", UUID, sa.ForeignKey("questions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.UniqueConstraint("question_id", "position", name="uq_question_option_position"),
    )
    op.create_table(
        "tags",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
    )
    op.create_table(
        "question_tags",
        sa.Column("question_id", UUID, sa.ForeignKey("questions.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tag_id", UUID, sa.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_table(
        "study_sessions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("learner_id", UUID, sa.ForeignKey("learners.id", ondelete="CASCADE"), nullable=False),
        sa.Column("settings", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "review_states",
        sa.Column("learner_id", UUID, sa.ForeignKey("learners.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("question_id", UUID, sa.ForeignKey("questions.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("algorithm_version", sa.String(32), nullable=False, server_default="ponkan-srs-v1"),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stability", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("difficulty", sa.Float(), nullable=False, server_default="5.0"),
        sa.Column("reps", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lapses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("streak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_rating", sa.Integer()),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("avg_response_ms", sa.Float(), nullable=False, server_default="0"),
        sa.Column("mastery", sa.String(24), nullable=False, server_default="weak"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_review_state_due", "review_states", ["learner_id", "due_at"])
    op.create_table(
        "review_events",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("learner_id", UUID, sa.ForeignKey("learners.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_id", UUID, sa.ForeignKey("questions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", UUID, sa.ForeignKey("study_sessions.id", ondelete="SET NULL")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column("response_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mode", sa.String(32), nullable=False, server_default="choice"),
        sa.Column("scheduled_days", sa.Float(), nullable=False, server_default="0"),
        sa.Column("stability_before", sa.Float(), nullable=False),
        sa.Column("stability_after", sa.Float(), nullable=False),
        sa.Column("difficulty_before", sa.Float(), nullable=False),
        sa.Column("difficulty_after", sa.Float(), nullable=False),
        sa.Column("metadata", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.CheckConstraint("rating BETWEEN 1 AND 4", name="ck_review_rating"),
    )
    op.create_index("ix_review_event_time", "review_events", ["learner_id", "reviewed_at"])
    op.create_table(
        "sync_runs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("import_source_id", UUID, sa.ForeignKey("import_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(32), nullable=False, server_default="running"),
        sa.Column("seen_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("archived_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_table("sync_runs")
    op.drop_index("ix_review_event_time", table_name="review_events")
    op.drop_table("review_events")
    op.drop_index("ix_review_state_due", table_name="review_states")
    op.drop_table("review_states")
    op.drop_table("study_sessions")
    op.drop_table("question_tags")
    op.drop_table("tags")
    op.drop_table("question_options")
    op.drop_index("ix_question_material_active", table_name="questions")
    op.drop_table("questions")
    op.drop_table("import_sources")
    op.drop_table("materials")
    op.drop_table("learners")
