from typing import Any
from app.extensions import db
from app.models.base import TenantMixin

class Space(TenantMixin, db.Model):
    """
    Dining zone/space within a restaurant (e.g., Ground Floor, AC Dining, Rooftop).
    """
    __tablename__ = 'spaces'

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

    name = db.Column(db.String(100), nullable=False)

    # Relationships
    tables = db.relationship('Table', backref='space', lazy='dynamic', cascade='all, delete-orphan')

    __table_args__ = (
        db.UniqueConstraint('restaurant_id', 'name', name='uq_space_restaurant_name'),
    )

    def __repr__(self):
        return f"<Space {self.id}: {self.name}>"

class Table(TenantMixin, db.Model):
    """
    Individual dining table entity.
    """
    __tablename__ = 'tables'

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

    space_id = db.Column(db.Integer, db.ForeignKey('spaces.id', ondelete='CASCADE'), nullable=False, index=True)
    name = db.Column(db.String(50), nullable=False)  # e.g., 'T-01', 'VIP-2'
    capacity = db.Column(db.Integer, default=4, nullable=False)
    cover_charge = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)  # BDT ৳ (Rule 3)
    status = db.Column(db.String(20), default='open', nullable=False)  # 'open', 'occupied'

    # Relationships
    orders = db.relationship('Order', backref='table', lazy='dynamic', passive_deletes=True)

    __table_args__ = (
        db.UniqueConstraint('restaurant_id', 'space_id', 'name', name='uq_table_restaurant_space_name'),
        db.CheckConstraint('capacity > 0', name='ck_table_capacity_positive'),
        db.CheckConstraint('cover_charge >= 0', name='ck_table_cover_charge_positive'),
        db.Index('ix_table_restaurant_status', 'restaurant_id', 'status'),
    )

    def __repr__(self):
        return f"<Table {self.id}: {self.name} ({self.status})>"

