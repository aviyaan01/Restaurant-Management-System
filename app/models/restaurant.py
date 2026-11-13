from typing import Any
from app.extensions import db
from app.models.base import TimestampMixin

class Restaurant(TimestampMixin, db.Model):
    """
    Tenant root entity representing an individual restaurant establishment.
    Holds tax (BIN, VAT rate), pricing configuration, and receipt customization.
    """
    __tablename__ = 'restaurants'

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

    name = db.Column(db.String(150), nullable=False)
    address = db.Column(db.Text, nullable=True)
    phone = db.Column(db.String(30), nullable=True)
    bin = db.Column(db.String(50), nullable=True)  # Bangladeshi Business Identification Number
    vat_rate = db.Column(db.Numeric(5, 2), default=5.00, nullable=False)  # e.g., 5.00 for 5% VAT
    price_mode = db.Column(db.String(20), default='exclusive', nullable=False)  # 'inclusive' or 'exclusive'
    receipt_footer = db.Column(db.Text, nullable=True)  # e.g., "ধন্যবাদ, আবার আসবেন!"

    # Relationships
    users = db.relationship('User', backref='restaurant', lazy='dynamic', cascade='all, delete-orphan')
    categories = db.relationship('Category', backref='restaurant', lazy='dynamic', cascade='all, delete-orphan')
    dishes = db.relationship('Dish', backref='restaurant', lazy='dynamic', cascade='all, delete-orphan')
    spaces = db.relationship('Space', backref='restaurant', lazy='dynamic', cascade='all, delete-orphan')
    tables = db.relationship('Table', backref='restaurant', lazy='dynamic', cascade='all, delete-orphan')
    orders = db.relationship('Order', backref='restaurant', lazy='dynamic', cascade='all, delete-orphan')
    payments = db.relationship('Payment', backref='restaurant', lazy='dynamic', cascade='all, delete-orphan')
    finance_entries = db.relationship('FinanceEntry', backref='restaurant', lazy='dynamic', cascade='all, delete-orphan')
    audit_logs = db.relationship('AuditLog', backref='restaurant', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<Restaurant {self.id}: {self.name}>"

