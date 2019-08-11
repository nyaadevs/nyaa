"""Add trusted applications

Revision ID: 5cbcee17bece
Revises: 8a6a7662eb37
Create Date: 2018-11-05 15:16:07.497898

"""
from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils


# revision identifiers, used by Alembic.
revision = '5cbcee17bece'
down_revision = '8a6a7662eb37'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('trusted_applications',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('submitter_id', sa.Integer(), nullable=False, index=True),
    sa.Column('created_time', sa.DateTime(), nullable=True),
    sa.Column('closed_time', sa.DateTime(), nullable=True),
    sa.Column('why_want', sa.String(length=4000), nullable=False),
    sa.Column('why_give', sa.String(length=4000), nullable=False),
    sa.Column('status', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['submitter_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('trusted_reviews',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('reviewer_id', sa.Integer(), nullable=False),
    sa.Column('app_id', sa.Integer(), nullable=False),
    sa.Column('created_time', sa.DateTime(), nullable=True),
    sa.Column('comment', sa.String(length=4000), nullable=False),
    sa.Column('recommendation', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['app_id'], ['trusted_applications.id'], ),
    sa.ForeignKeyConstraint(['reviewer_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('trusted_reviews')
    op.drop_table('trusted_applications')
