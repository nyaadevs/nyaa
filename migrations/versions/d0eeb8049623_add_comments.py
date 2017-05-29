"""Add comments table.

Revision ID: d0eeb8049623
Revises: 3001f79b7722
Create Date: 2017-05-22 22:58:12.039149

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd0eeb8049623'
down_revision = '3001f79b7722'
branch_labels = None
depends_on = None

TABLE_PREFIXES = ('nyaa', 'sukebei')


def upgrade():
    for prefix in TABLE_PREFIXES:
        op.create_table(prefix + '_comments',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('torrent_id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=True),
            sa.Column('created_time', sa.DateTime(), nullable=True),
            sa.Column('text', sa.String(length=255, collation='utf8mb4_bin'), nullable=False),
            sa.ForeignKeyConstraint(['torrent_id'], [prefix + '_torrents.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )


def downgrade():
    for prefix in TABLE_PREFIXES:
        op.drop_table(prefix + '_comments')
