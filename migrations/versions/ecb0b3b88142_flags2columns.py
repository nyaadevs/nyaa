"""Convert bitflags to seperate indexed columns

Revision ID: ecb0b3b88142
Revises: 6cc823948c5a
Create Date: 2018-04-08 02:52:44.178958

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql
import sys

# revision identifiers, used by Alembic.
revision = 'ecb0b3b88142'
down_revision = '6cc823948c5a'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE nyaa_torrents "
        "ADD COLUMN anonymous BOOL NOT NULL, "
        "ADD COLUMN banned BOOL NOT NULL, "
        "ADD COLUMN comment_locked BOOL NOT NULL, "
        "ADD COLUMN complete BOOL NOT NULL, "
        "ADD COLUMN deleted BOOL NOT NULL, "
        "ADD COLUMN hidden BOOL NOT NULL, "
        "ADD COLUMN remake BOOL NOT NULL, "
        "ADD COLUMN trusted BOOL NOT NULL;"
    )

    op.create_index(op.f('ix_nyaa_torrents_anonymous'), 'nyaa_torrents', ['anonymous'], unique=False)
    op.create_index(op.f('ix_nyaa_torrents_banned'), 'nyaa_torrents', ['banned'], unique=False)
    op.create_index(op.f('ix_nyaa_torrents_comment_locked'), 'nyaa_torrents', ['comment_locked'], unique=False)
    op.create_index(op.f('ix_nyaa_torrents_complete'), 'nyaa_torrents', ['complete'], unique=False)
    op.create_index(op.f('ix_nyaa_torrents_deleted'), 'nyaa_torrents', ['deleted'], unique=False)
    op.create_index(op.f('ix_nyaa_torrents_hidden'), 'nyaa_torrents', ['hidden'], unique=False)
    op.create_index(op.f('ix_nyaa_torrents_remake'), 'nyaa_torrents', ['remake'], unique=False)
    op.create_index(op.f('ix_nyaa_torrents_trusted'), 'nyaa_torrents', ['trusted'], unique=False)

    op.drop_index('ix_nyaa_torrents_flags', table_name='nyaa_torrents')
    op.create_index(op.f('ix_nyaa_torrents_uploader_id'), 'nyaa_torrents', ['uploader_id'], unique=False)
    op.drop_index('uploader_flag_idx', table_name='nyaa_torrents')
    op.create_index('ix_nyaa_super', 'nyaa_torrents', ['id', 'uploader_id', 'main_category_id', 'sub_category_id', 'anonymous', 'hidden', 'deleted', 'banned', 'trusted', 'remake', 'complete'], unique=False)

    op.execute('UPDATE nyaa_torrents SET anonymous = TRUE WHERE flags & 1 IS TRUE;')
    op.execute('UPDATE nyaa_torrents SET hidden = TRUE WHERE flags & 2 IS TRUE;')
    op.execute('UPDATE nyaa_torrents SET trusted = TRUE WHERE flags & 4 IS TRUE;')
    op.execute('UPDATE nyaa_torrents SET remake = TRUE WHERE flags & 8 IS TRUE;')
    op.execute('UPDATE nyaa_torrents SET complete = TRUE WHERE flags & 16 IS TRUE;')
    op.execute('UPDATE nyaa_torrents SET deleted = TRUE WHERE flags & 32 IS TRUE;')
    op.execute('UPDATE nyaa_torrents SET banned = TRUE WHERE flags & 64 IS TRUE;')
    op.execute('UPDATE nyaa_torrents SET comment_locked = TRUE WHERE flags & 128 IS TRUE;')

    #op.drop_column('nyaa_torrents', 'flags')

    op.execute(
        "ALTER TABLE sukebei_torrents "
        "ADD COLUMN anonymous BOOL NOT NULL, "
        "ADD COLUMN banned BOOL NOT NULL, "
        "ADD COLUMN comment_locked BOOL NOT NULL, "
        "ADD COLUMN complete BOOL NOT NULL, "
        "ADD COLUMN deleted BOOL NOT NULL, "
        "ADD COLUMN hidden BOOL NOT NULL, "
        "ADD COLUMN remake BOOL NOT NULL, "
        "ADD COLUMN trusted BOOL NOT NULL;"
    )

    op.create_index(op.f('ix_sukebei_torrents_anonymous'), 'sukebei_torrents', ['anonymous'], unique=False)
    op.create_index(op.f('ix_sukebei_torrents_banned'), 'sukebei_torrents', ['banned'], unique=False)
    op.create_index(op.f('ix_sukebei_torrents_comment_locked'), 'sukebei_torrents', ['comment_locked'], unique=False)
    op.create_index(op.f('ix_sukebei_torrents_complete'), 'sukebei_torrents', ['complete'], unique=False)
    op.create_index(op.f('ix_sukebei_torrents_deleted'), 'sukebei_torrents', ['deleted'], unique=False)
    op.create_index(op.f('ix_sukebei_torrents_hidden'), 'sukebei_torrents', ['hidden'], unique=False)
    op.create_index(op.f('ix_sukebei_torrents_remake'), 'sukebei_torrents', ['remake'], unique=False)
    op.create_index(op.f('ix_sukebei_torrents_trusted'), 'sukebei_torrents', ['trusted'], unique=False)

    op.drop_index('ix_sukebei_torrents_flags', table_name='sukebei_torrents')
    op.create_index(op.f('ix_sukebei_torrents_uploader_id'), 'sukebei_torrents', ['uploader_id'], unique=False)
    op.drop_index('uploader_flag_idx', table_name='sukebei_torrents')
    op.create_index('ix_sukebei_super', 'sukebei_torrents', ['id', 'uploader_id', 'main_category_id', 'sub_category_id', 'anonymous', 'hidden', 'deleted', 'banned', 'trusted', 'remake', 'complete'], unique=False)

    op.execute('UPDATE sukebei_torrents SET anonymous = TRUE WHERE flags & 1 IS TRUE;')
    op.execute('UPDATE sukebei_torrents SET hidden = TRUE WHERE flags & 2 IS TRUE;')
    op.execute('UPDATE sukebei_torrents SET trusted = TRUE WHERE flags & 4 IS TRUE;')
    op.execute('UPDATE sukebei_torrents SET remake = TRUE WHERE flags & 8 IS TRUE;')
    op.execute('UPDATE sukebei_torrents SET complete = TRUE WHERE flags & 16 IS TRUE;')
    op.execute('UPDATE sukebei_torrents SET deleted = TRUE WHERE flags & 32 IS TRUE;')
    op.execute('UPDATE sukebei_torrents SET banned = TRUE WHERE flags & 64 IS TRUE;')
    op.execute('UPDATE sukebei_torrents SET comment_locked = TRUE WHERE flags & 128 IS TRUE;')

    #op.drop_column('sukebei_torrents', 'flags')


def downgrade():
    print("downgrade not supported")
    sys.exit(1)
