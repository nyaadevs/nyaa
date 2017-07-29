"""Add is_webseed to Trackers

Revision ID: ffd23e570f92
Revises: 1add911660a6
Create Date: 2017-07-29 19:03:58.244769

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ffd23e570f92'
down_revision = '1add911660a6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('trackers', sa.Column('is_webseed', sa.Boolean(), nullable=False))


def downgrade():
    op.drop_column('trackers', 'is_webseed')
