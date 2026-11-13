from typing import Any
from app.extensions import db
from app.models.base import TenantMixin

class Category(TenantMixin, db.Model):
    """
    Menu category entity (e.g. Biryani, Appetizers, Beverages, Desserts).
    """
    __tablename__ = 'categories'

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

    name = db.Column(db.String(100), nullable=False)
    sort_order = db.Column(db.Integer, default=0, nullable=False)

    # Relationships
    dishes = db.relationship('Dish', backref='category', lazy='dynamic')

    __table_args__ = (
        db.UniqueConstraint('restaurant_id', 'name', name='uq_category_restaurant_name'),
        db.Index('ix_category_restaurant_sort', 'restaurant_id', 'sort_order'),
    )

    def __repr__(self):
        return f"<Category {self.id}: {self.name}>"

class Dish(TenantMixin, db.Model):
    """
    Menu item entity.
    Prices are stored as Numeric(12, 2) BDT (Rule 3).
    """
    __tablename__ = 'dishes'

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

    category_id = db.Column(db.Integer, db.ForeignKey('categories.id', ondelete='SET NULL'), nullable=True, index=True)
    name = db.Column(db.String(150), nullable=False)
    price = db.Column(db.Numeric(12, 2), nullable=False)  # BDT ৳ (Rule 3)
    discount = db.Column(db.Numeric(12, 2), default=0.00, nullable=False)  # BDT ৳ discount
    veg_type = db.Column(db.String(20), default='non_veg', nullable=False)  # 'veg', 'non_veg', 'egg'
    prep_time_minutes = db.Column(db.Integer, default=15, nullable=False)
    is_available = db.Column(db.Boolean, default=True, nullable=False)
    is_archived = db.Column(db.Boolean, default=False, nullable=False)

    __table_args__ = (
        db.CheckConstraint('price >= 0', name='ck_dish_price_positive'),
        db.CheckConstraint('discount >= 0', name='ck_dish_discount_positive'),
        db.Index('ix_dish_restaurant_available', 'restaurant_id', 'is_available', 'is_archived'),
        db.Index('ix_dish_restaurant_category', 'restaurant_id', 'category_id'),
    )

    def __repr__(self):
        return f"<Dish {self.id}: {self.name} (৳{self.price})>"

