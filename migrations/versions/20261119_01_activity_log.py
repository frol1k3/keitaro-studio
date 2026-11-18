"""Create activity log.

Revision ID: 20261119_01
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "20261119_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "activity_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("stream_id", sa.Integer(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("activity_log")
