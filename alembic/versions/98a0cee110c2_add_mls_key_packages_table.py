"""add mls_key_packages table

Revision ID: 98a0cee110c2
Revises: 9713e33403d0
Create Date: 2026-02-27 19:07:33.751980

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '98a0cee110c2'
down_revision: Union[str, Sequence[str], None] = '9713e33403d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('mls_key_packages',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('device_id', sa.String(length=255), nullable=False),
    sa.Column('key_data', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['device_id'], ['devices.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_mls_key_packages_device_id'), 'mls_key_packages', ['device_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_mls_key_packages_device_id'), table_name='mls_key_packages')
    op.drop_table('mls_key_packages')
