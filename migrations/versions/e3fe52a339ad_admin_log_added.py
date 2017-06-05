"""Admin log added

Revision ID: e3fe52a339ad
Revises: 7f064e009cab
Create Date: 2017-06-05 04:07:21.072430

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'e3fe52a339ad'
down_revision = '7f064e009cab'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('nyaa_adminlog',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('created_time', sa.DateTime(), nullable=True),
    sa.Column('log_type', sa.Integer(), nullable=False),
    sa.Column('torrent_id', sa.Integer(), nullable=True),
    sa.Column('comment_id', sa.Integer(), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('admin_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['admin_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['comment_id'], ['nyaa_comments.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['torrent_id'], ['nyaa_torrents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('sukebei_adminlog',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('created_time', sa.DateTime(), nullable=True),
    sa.Column('log_type', sa.Integer(), nullable=False),
    sa.Column('torrent_id', sa.Integer(), nullable=True),
    sa.Column('comment_id', sa.Integer(), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('admin_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['admin_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['comment_id'], ['sukebei_comments.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['torrent_id'], ['sukebei_torrents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('sukebei_adminlog')
    op.drop_table('nyaa_adminlog')
    # ### end Alembic commands ###