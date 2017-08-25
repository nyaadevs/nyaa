"""Add bans table

Revision ID: 500117641608
Revises: b79d2fcafd88
Create Date: 2017-08-17 01:44:39.205126

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '500117641608'
down_revision = 'b79d2fcafd88'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('bans',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('created_time', sa.DateTime(), nullable=True),
    sa.Column('admin_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('user_ip', sa.Binary(length=16), nullable=True),
    sa.Column('reason', sa.String(length=2048), nullable=False),
    sa.ForeignKeyConstraint(['admin_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('user_ip_16', 'bans', ['user_ip'], unique=True, mysql_length=16)
    op.create_index('user_ip_4', 'bans', ['user_ip'], unique=True, mysql_length=4)


def downgrade():
    op.drop_index('user_ip_4', table_name='bans')
    op.drop_index('user_ip_16', table_name='bans')
    op.drop_table('bans')
