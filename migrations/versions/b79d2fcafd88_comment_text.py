"""Change comment text field from VARCHAR(255) to mysql.TEXT

Revision ID: b79d2fcafd88
Revises: ffd23e570f92
Create Date: 2017-08-14 18:57:44.165168

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = 'b79d2fcafd88'
down_revision = 'ffd23e570f92'
branch_labels = None
depends_on = None

TABLE_PREFIXES = ('nyaa', 'sukebei')

def upgrade():
    for prefix in TABLE_PREFIXES:
        op.alter_column(prefix + '_comments', 'text',
                   existing_type=mysql.VARCHAR(charset='utf8mb4', collation='utf8mb4_bin', length=255),
                   type_=mysql.TEXT(collation='utf8mb4_bin'),
                   existing_nullable=False)


def downgrade():
    for prefix in TABLE_PREFIXES:
        op.alter_column(prefix + '_comments', 'text',
                   existing_type=mysql.TEXT(collation='utf8mb4_bin'),
                   type_=mysql.VARCHAR(charset='utf8mb4', collation='utf8mb4_bin', length=255),
                   existing_nullable=False)
