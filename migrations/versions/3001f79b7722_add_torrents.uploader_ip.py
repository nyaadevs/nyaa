"""Add uploader_ip column to torrents table.

Revision ID: 3001f79b7722
Revises:
Create Date: 2017-05-21 18:01:35.472717

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3001f79b7722'
down_revision = '97ddefed1834'
branch_labels = None
depends_on = None

TABLE_PREFIXES = ('nyaa', 'sukebei')


def upgrade():

    for prefix in TABLE_PREFIXES:
        op.add_column(prefix + '_torrents', sa.Column('uploader_ip', sa.Binary(), nullable=True))
        # ### end Alembic commands ###


def downgrade():
    for prefix in TABLE_PREFIXES:
        op.drop_column(prefix + '_torrents', 'uploader_ip')
