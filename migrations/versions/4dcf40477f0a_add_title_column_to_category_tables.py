"""Add title column to category tables

Revision ID: 4dcf40477f0a
Revises: ffd23e570f92
Create Date: 2017-07-30 22:57:46.524459

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4dcf40477f0a'
down_revision = 'ffd23e570f92'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('nyaa_main_categories', sa.Column('title', sa.String(length=64), nullable=False))
    op.add_column('nyaa_sub_categories', sa.Column('title', sa.String(length=64), nullable=False))
    op.add_column('sukebei_main_categories', sa.Column('title', sa.String(length=64), nullable=False))
    op.add_column('sukebei_sub_categories', sa.Column('title', sa.String(length=64), nullable=False))

    # Insert values for the new title column
    for table_name in ('nyaa_main', 'nyaa_sub', 'sukebei_main', 'sukebei_sub'):
        # Copy name to title for starters
        update = 'UPDATE {t}_categories'.format(t=table_name)
        op.execute(update + ' SET title = name;'.format(t=table_name))

        # Only need to do this for sub-categories
        if table_name in ('nyaa_sub', 'sukebei_sub'):
            op.execute(update + ' SET title = "English" WHERE name = "English-translated";')
            op.execute(update + ' SET title = "Non-English" WHERE name = "Non-English-translated";')
            op.execute(update + ' SET title = "AMV" WHERE name = "Anime Music Video";')
            op.execute(update + ' SET title = "Idol/PV" WHERE name = "Idol/Promotional Video";')
            op.execute(update + ' SET title = "Apps" WHERE name = "Applications";')
            op.execute(update + ' SET title = "Pictures" WHERE name LIKE "Photobooks%Pictures";')


def downgrade():
    op.drop_column('sukebei_sub_categories', 'title')
    op.drop_column('sukebei_main_categories', 'title')
    op.drop_column('nyaa_sub_categories', 'title')
    op.drop_column('nyaa_main_categories', 'title')
