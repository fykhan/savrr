import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

metadata = sa.MetaData()

profiles = sa.Table(
    "profiles",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("currency", sa.String, nullable=False),
    sa.Column("name", sa.String, nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)
