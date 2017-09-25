"""Notifications added

Revision ID: 306b45f72b8c
Revises: 500117641608
Create Date: 2017-09-19 11:49:33.831214

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '306b45f72b8c'
down_revision = '500117641608'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('nyaa_notifications',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('created_time', sa.DateTime(), nullable=True),
    sa.Column('body', sa.String(length=1024), nullable=False),
    sa.Column('type', sa.String(length=50), nullable=False),
    sa.Column('read', sa.Boolean(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('torrent_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['torrent_id'], ['nyaa_torrents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_nyaa_notifications_read'), 'nyaa_notifications', ['read'], unique=False)
    op.create_table('sukebei_notifications',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('created_time', sa.DateTime(), nullable=True),
    sa.Column('body', sa.String(length=1024), nullable=False),
    sa.Column('type', sa.String(length=50), nullable=False),
    sa.Column('read', sa.Boolean(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('torrent_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['torrent_id'], ['sukebei_torrents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_sukebei_notifications_read'), 'sukebei_notifications', ['read'], unique=False)
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_sukebei_notifications_read'), table_name='sukebei_notifications')
    op.drop_table('sukebei_notifications')
    op.drop_index(op.f('ix_nyaa_notifications_read'), table_name='nyaa_notifications')
    op.drop_table('nyaa_notifications')
    # ### end Alembic commands ###