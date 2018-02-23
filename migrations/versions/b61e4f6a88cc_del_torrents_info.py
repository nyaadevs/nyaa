"""Remove bencoded info dicts from mysql

Revision ID: b61e4f6a88cc
Revises: cf7bf6d0e6bd
Create Date: 2017-08-29 01:45:08.357936

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql
import sys

# revision identifiers, used by Alembic.
revision = 'b61e4f6a88cc'
down_revision = 'cf7bf6d0e6bd'
branch_labels = None
depends_on = None


def upgrade():
    print("--- WARNING ---")
    print("This migration drops the torrent_info tables.")
    print("You will lose all of your .torrent files if you have not converted them beforehand.")
    print("Use the migration script at utils/infodict_mysql2file.py")
    print("Type OKAY and hit Enter to continue, CTRL-C to abort.")
    print("--- WARNING ---")
    try:
        if input() != "OKAY":
            sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(1)

    op.drop_table('sukebei_torrents_info')
    op.drop_table('nyaa_torrents_info')


def downgrade():
    op.create_table('nyaa_torrents_info',
    sa.Column('info_dict', mysql.MEDIUMBLOB(), nullable=True),
    sa.Column('torrent_id', mysql.INTEGER(display_width=11), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['torrent_id'], ['nyaa_torrents.id'], name='nyaa_torrents_info_ibfk_1', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('torrent_id'),
    mysql_collate='utf8_bin',
    mysql_default_charset='utf8',
    mysql_engine='InnoDB',
    mysql_row_format='COMPRESSED'
    )
    op.create_table('sukebei_torrents_info',
    sa.Column('info_dict', mysql.MEDIUMBLOB(), nullable=True),
    sa.Column('torrent_id', mysql.INTEGER(display_width=11), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['torrent_id'], ['sukebei_torrents.id'], name='sukebei_torrents_info_ibfk_1', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('torrent_id'),
    mysql_collate='utf8_bin',
    mysql_default_charset='utf8',
    mysql_engine='InnoDB',
    mysql_row_format='COMPRESSED'
    )
