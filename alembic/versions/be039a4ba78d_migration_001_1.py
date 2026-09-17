"""migration 001/1

Revision ID: be039a4ba78d
Revises: f81ce12b3af3
Create Date: 2026-09-17 18:08:19.848101

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'be039a4ba78d'
down_revision: Union[str, Sequence[str], None] = 'f81ce12b3af3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### Création de la table event_pictures ###
    op.create_table(
        'event_pictures',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('event_id', sa.String(), nullable=False),
        sa.Column('url', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### Suppression de la table event_pictures ###
    op.drop_table('event_pictures')
    # ### end Alembic commands ###