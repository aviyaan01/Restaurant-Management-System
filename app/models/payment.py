from app.extensions import db
from app.models.base import TenantMixin

class Payment(TenantMixin, db.Model):
    """
    Payment transaction record for an Order.
    Supports split payments across multiple methods: Cash, bKash, Nagad, Card.
    """
    __tablename__ = 'payments'

    order_id = db.Column(db.Integer, db.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False, index=True)
    method = db.Column(db.String(20), nullable=False)  # 'cash', 'bkash', 'nagad', 'card'
    amount = db.Column(db.Numeric(12, 2), nullable=False)  # BDT ৳ (Rule 3)
    status = db.Column(db.String(20), default='completed', nullable=False)  # 'completed', 'refunded', 'voided'
    reference = db.Column(db.String(100), nullable=True)  # bKash TrxID, Nagad TrxID, or Card last 4 digits
    received_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)

    # Relationships
    receiver = db.relationship('User', foreign_keys=[received_by])

    __table_args__ = (
        db.CheckConstraint('amount > 0', name='ck_payment_amount_positive'),
        db.Index('ix_payment_restaurant_method', 'restaurant_id', 'method', 'created_at'),
    )

    def __repr__(self):
        return f"<Payment {self.id}: {self.method} ৳{self.amount} ({self.status})>"

