from datetime import datetime, timezone
from app.extensions import db
from app.models.base import TenantMixin

class FinanceEntry(TenantMixin, db.Model):
    """
    Financial cashbook ledger entry for daily operations:
    Sales revenue, petty-cash purchases (raw ingredients), and operational expenses (utility, rent, wages).
    """
    __tablename__ = 'finance_entries'

    type = db.Column(db.String(20), nullable=False)  # 'sale', 'purchase', 'expense'
    amount = db.Column(db.Numeric(12, 2), nullable=False)  # BDT ৳ (Rule 3)
    note = db.Column(db.Text, nullable=True)  # Description e.g., "Daily chicken & vegetable market buy"
    entry_date = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id', ondelete='SET NULL'), nullable=True, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)

    # Relationships
    order = db.relationship('Order')
    creator = db.relationship('User', foreign_keys=[created_by])

    __table_args__ = (
        db.CheckConstraint('amount > 0', name='ck_finance_amount_positive'),
        db.Index('ix_finance_restaurant_type_date', 'restaurant_id', 'type', 'entry_date'),
    )

    def __repr__(self):
        return f"<FinanceEntry {self.id}: {self.type} ৳{self.amount}>"

