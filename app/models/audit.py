from datetime import datetime, timezone
from typing import Any
from app.extensions import db

class AuditLog(db.Model):
    """
    Non-negotiable Rule 5: Financial and staff changes are written to an audit log with user and time.
    Immutable log capturing who changed what and when within a restaurant tenant.
    """
    __tablename__ = 'audit_logs'

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    restaurant_id = db.Column(
        db.Integer,
        db.ForeignKey('restaurants.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    action = db.Column(db.String(100), nullable=False)  # e.g., 'STAFF_ROLE_CHANGED', 'ORDER_CANCELLED', 'PRICE_UPDATED'
    record_type = db.Column(db.String(50), nullable=False)  # e.g., 'User', 'Order', 'Payment', 'Dish'
    record_id = db.Column(db.Integer, nullable=True)
    details = db.Column(db.JSON, nullable=True)  # JSON payload capturing previous vs updated values
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    # Relationships
    user = db.relationship('User', foreign_keys=[user_id])

    __table_args__ = (
        db.Index('ix_audit_restaurant_created', 'restaurant_id', 'created_at'),
        db.Index('ix_audit_restaurant_record', 'restaurant_id', 'record_type', 'record_id'),
    )

    def __repr__(self):
        return f"<AuditLog {self.id}: {self.action} on {self.record_type}#{self.record_id} by User#{self.user_id}>"

