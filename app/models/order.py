from app.extensions import db
from app.models.base import TenantMixin

class Order(TenantMixin, db.Model):
    """
    Core POS sales order entity.
    Sequential order_no unique per restaurant tenant.
    All financial totals stored as exact Numeric(12, 2) in BDT (Rule 3).
    """
    __tablename__ = 'orders'

    order_no = db.Column(db.Integer, nullable=False)
    type = db.Column(db.String(20), nullable=False)  # 'dine_in', 'take_away', 'quick'
    table_id = db.Column(db.Integer, db.ForeignKey('tables.id', ondelete='SET NULL'), nullable=True, index=True)
    status = db.Column(db.String(20), default='open', nullable=False)  # 'open', 'paid', 'cancelled'
    
    # Financial breakdown in BDT (Rule 3)
    subtotal = db.Column(db.Numeric(12, 2), default=0.00, nullable=False)
    discount = db.Column(db.Numeric(12, 2), default=0.00, nullable=False)
    cover_charge = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    vat_amount = db.Column(db.Numeric(12, 2), default=0.00, nullable=False)
    total = db.Column(db.Numeric(12, 2), default=0.00, nullable=False)

    payment_status = db.Column(db.String(20), default='unpaid', nullable=False)  # 'unpaid', 'partial', 'paid'
    cancel_reason = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    paid_at = db.Column(db.DateTime(timezone=True), nullable=True)

    # Relationships
    items = db.relationship('OrderItem', backref='order', lazy='dynamic', cascade='all, delete-orphan')
    payments = db.relationship('Payment', backref='order', lazy='dynamic', cascade='all, delete-orphan')
    creator = db.relationship('User', foreign_keys=[created_by])

    __table_args__ = (
        db.UniqueConstraint('restaurant_id', 'order_no', name='uq_order_restaurant_order_no'),
        db.CheckConstraint('subtotal >= 0', name='ck_order_subtotal_positive'),
        db.CheckConstraint('discount >= 0', name='ck_order_discount_positive'),
        db.CheckConstraint('vat_amount >= 0', name='ck_order_vat_positive'),
        db.CheckConstraint('total >= 0', name='ck_order_total_positive'),
        db.Index('ix_order_restaurant_status', 'restaurant_id', 'status', 'payment_status'),
        db.Index('ix_order_restaurant_created', 'restaurant_id', 'created_at'),
    )

    def __repr__(self):
        return f"<Order #{self.order_no} ({self.type}) - ৳{self.total}>"

class OrderItem(TenantMixin, db.Model):
    """
    Individual line item in an Order.
    Crucial Design Decision:
    Stores dish_name_snapshot and unit_price_snapshot to freeze the historical financial truth
    at the exact moment of sale, unaffected by future dish price changes or menu alterations.
    """
    __tablename__ = 'order_items'

    order_id = db.Column(db.Integer, db.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False, index=True)
    dish_id = db.Column(db.Integer, db.ForeignKey('dishes.id', ondelete='SET NULL'), nullable=True, index=True)
    
    # Immutable historical snapshots
    dish_name_snapshot = db.Column(db.String(150), nullable=False)
    unit_price_snapshot = db.Column(db.Numeric(12, 2), nullable=False)  # BDT ৳ (Rule 3)
    
    quantity = db.Column(db.Integer, default=1, nullable=False)
    note = db.Column(db.String(255), nullable=True)  # Special instructions e.g. "Less chili"
    kitchen_status = db.Column(db.String(20), default='new', nullable=False)  # 'new', 'preparing', 'ready'

    # Relationships
    dish = db.relationship('Dish')

    __table_args__ = (
        db.CheckConstraint('quantity > 0', name='ck_order_item_quantity_positive'),
        db.CheckConstraint('unit_price_snapshot >= 0', name='ck_order_item_price_positive'),
        db.Index('ix_order_item_restaurant_kitchen', 'restaurant_id', 'kitchen_status'),
        db.Index('ix_order_item_order_kitchen', 'order_id', 'kitchen_status'),
    )

    @property
    def line_total(self):
        return self.unit_price_snapshot * self.quantity

    def __repr__(self):
        return f"<OrderItem {self.id}: {self.dish_name_snapshot} x{self.quantity}>"

