"""Initial database state

Revision ID: 97ddefed1834
Revises: 
Create Date: 2017-05-26 18:46:14.440040

"""
from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '97ddefed1834'
down_revision = None
branch_labels = None
depends_on = None

TABLE_PREFIXES = ('nyaa', 'sukebei')

def upgrade():
    # Shared tables
    op.create_table('users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(length=32, collation='ascii_general_ci'), nullable=False),
        sa.Column('email', sqlalchemy_utils.types.email.EmailType(length=255), nullable=True),
        
        # These are actually PasswordType, UserStatusType and UserLevelType,
        # but database-wise binary and integers are what's being used
        sa.Column('password_hash', sa.Binary(length=255), nullable=False),
        sa.Column('status', sa.Integer(), nullable=False),
        sa.Column('level', sa.Integer(), nullable=False),

        sa.Column('created_time', sa.DateTime(), nullable=True),
        sa.Column('last_login_date', sa.DateTime(), nullable=True),
        sa.Column('last_login_ip', sa.Binary(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
        sa.UniqueConstraint('username')
    )

    op.create_table('trackers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('uri', sa.String(length=255, collation='utf8_general_ci'), nullable=False),
        sa.Column('disabled', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('uri')
    )

    # Nyaa and Sukebei
    for prefix in TABLE_PREFIXES:
        # Main categories
        op.create_table(prefix + '_main_categories',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=64), nullable=False),
            sa.PrimaryKeyConstraint('id')
        )
        # Sub categories
        op.create_table(prefix + '_sub_categories',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('main_category_id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=64), nullable=False),
            sa.ForeignKeyConstraint(['main_category_id'], [prefix + '_main_categories.id'], ),
            sa.PrimaryKeyConstraint('id', 'main_category_id')
        )
        # Main torrent table
        op.create_table(prefix + '_torrents',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('info_hash', sa.BINARY(length=20), nullable=False),
            sa.Column('display_name', sa.String(length=255, collation='utf8_general_ci'), nullable=False),
            sa.Column('torrent_name', sa.String(length=255), nullable=False),
            sa.Column('information', sa.String(length=255), nullable=False),
            sa.Column('description', mysql.TEXT(collation='utf8mb4_bin'), nullable=False),
            sa.Column('filesize', sa.BIGINT(), nullable=False),
            sa.Column('encoding', sa.String(length=32), nullable=False),
            sa.Column('flags', sa.Integer(), nullable=False),
            sa.Column('uploader_id', sa.Integer(), nullable=True),
            sa.Column('has_torrent', sa.Boolean(), nullable=False),
            sa.Column('created_time', sa.DateTime(), nullable=False),
            sa.Column('updated_time', sa.DateTime(), nullable=False),
            sa.Column('main_category_id', sa.Integer(), nullable=False),
            sa.Column('sub_category_id', sa.Integer(), nullable=False),
            sa.Column('redirect', sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(['main_category_id', 'sub_category_id'], [prefix + '_sub_categories.main_category_id', prefix + '_sub_categories.id'], ),
            sa.ForeignKeyConstraint(['main_category_id'], [prefix + '_main_categories.id'], ),
            sa.ForeignKeyConstraint(['redirect'], [prefix + '_torrents.id'], ),
            sa.ForeignKeyConstraint(['uploader_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_' + prefix + '_torrents_display_name'), prefix + '_torrents', ['display_name'], unique=False)
        op.create_index(op.f('ix_' + prefix + '_torrents_filesize'), prefix + '_torrents', ['filesize'], unique=False)
        op.create_index(op.f('ix_' + prefix + '_torrents_flags'), prefix + '_torrents', ['flags'], unique=False)
        op.create_index(op.f('ix_' + prefix + '_torrents_info_hash'), prefix + '_torrents', ['info_hash'], unique=True)
        op.create_index(prefix + '_uploader_flag_idx', prefix + '_torrents', ['uploader_id', 'flags'], unique=False)
        
        # Statistics for torrents
        op.create_table(prefix + '_statistics',
            sa.Column('torrent_id', sa.Integer(), nullable=False),
            sa.Column('seed_count', sa.Integer(), nullable=False),
            sa.Column('leech_count', sa.Integer(), nullable=False),
            sa.Column('download_count', sa.Integer(), nullable=False),
            sa.Column('last_updated', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['torrent_id'], [prefix + '_torrents.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('torrent_id')
        )
        op.create_index(op.f('ix_' + prefix + '_statistics_download_count'), prefix + '_statistics', ['download_count'], unique=False)
        op.create_index(op.f('ix_' + prefix + '_statistics_leech_count'), prefix + '_statistics', ['leech_count'], unique=False)
        op.create_index(op.f('ix_' + prefix + '_statistics_seed_count'), prefix + '_statistics', ['seed_count'], unique=False)
        
        # Trackers relationships for torrents
        op.create_table(prefix + '_torrent_trackers',
            sa.Column('torrent_id', sa.Integer(), nullable=False),
            sa.Column('tracker_id', sa.Integer(), nullable=False),
            sa.Column('order', sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(['torrent_id'], [prefix + '_torrents.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['tracker_id'], ['trackers.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('torrent_id', 'tracker_id')
        )
        op.create_index(op.f('ix_' + prefix + '_torrent_trackers_order'), prefix + '_torrent_trackers', ['order'], unique=False)
        
        # Torrent filelists
        op.create_table(prefix + '_torrents_filelist',
            sa.Column('torrent_id', sa.Integer(), nullable=False),
            sa.Column('filelist_blob', mysql.MEDIUMBLOB(), nullable=True),
            sa.ForeignKeyConstraint(['torrent_id'], [prefix + '_torrents.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('torrent_id'),
            mysql_row_format='COMPRESSED'
        )
        
        # Torrent info_dicts
        op.create_table(prefix + '_torrents_info',
            sa.Column('torrent_id', sa.Integer(), nullable=False),
            sa.Column('info_dict', mysql.MEDIUMBLOB(), nullable=True),
            sa.ForeignKeyConstraint(['torrent_id'], [prefix + '_torrents.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('torrent_id'),
            mysql_row_format='COMPRESSED'
        )
    # ### end Alembic commands ###


def downgrade():
    # Note: this may fail. It's better to just drop all tables instead (or reset the database)
    
    # Nyaa and Sukebei
    for prefix in TABLE_PREFIXES:
        op.drop_table(prefix + '_torrents_info')
        op.drop_table(prefix + '_torrents_filelist')
        op.drop_index(op.f('ix_' + prefix + '_torrent_trackers_order'), table_name=prefix + '_torrent_trackers')
        op.drop_table(prefix + '_torrent_trackers')
        op.drop_index(op.f('ix_' + prefix + '_statistics_seed_count'), table_name=prefix + '_statistics')
        op.drop_index(op.f('ix_' + prefix + '_statistics_leech_count'), table_name=prefix + '_statistics')
        op.drop_index(op.f('ix_' + prefix + '_statistics_download_count'), table_name=prefix + '_statistics')
        op.drop_table(prefix + '_statistics')
        op.drop_table(prefix + '_torrents')
        op.drop_index(prefix + '_uploader_flag_idx', table_name=prefix + '_torrents')
        op.drop_index(op.f('ix_' + prefix + '_torrents_info_hash'), table_name=prefix + '_torrents')
        op.drop_index(op.f('ix_' + prefix + '_torrents_flags'), table_name=prefix + '_torrents')
        op.drop_index(op.f('ix_' + prefix + '_torrents_filesize'), table_name=prefix + '_torrents')
        op.drop_index(op.f('ix_' + prefix + '_torrents_display_name'), table_name=prefix + '_torrents')
        op.drop_table(prefix + '_sub_categories')
        op.drop_table(prefix + '_main_categories')

    # Shared tables
    op.drop_table('users')
    op.drop_table('trackers')
    # ### end Alembic commands ###
