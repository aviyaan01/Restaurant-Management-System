from datetime import datetime, timezone
from sqlalchemy.orm import declared_attr
from app.extensions import db

class TimestampMixin:
    """Provides primary key and UTC timestamp tracking."""
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )

class TenantMixin(TimestampMixin):
    """
    Non-negotiable Rule 1: Every business table has restaurant_id and every query filters by it.
    Inherits id, created_at, updated_at and adds indexed restaurant_id foreign key.
    """
    @declared_attr
    def restaurant_id(cls):
        return db.Column(
            db.Integer,
            db.ForeignKey('restaurants.id', ondelete='CASCADE'),
            nullable=False,
            index=True
        )

