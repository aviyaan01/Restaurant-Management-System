from typing import Any
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app.extensions import db
from app.models.base import TenantMixin

class User(TenantMixin, UserMixin, db.Model):
    """
    User entity bound to a specific restaurant tenant.
    Roles: 'owner', 'manager', 'cashier', 'kitchen'
    """
    __tablename__ = 'users'

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30), nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'owner', 'manager', 'cashier', 'kitchen'
    pin_hash = db.Column(db.String(255), nullable=True)  # Fast tablet switcher (Phase 2)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    failed_login_count = db.Column(db.Integer, default=0, nullable=False)
    locked_until = db.Column(db.DateTime(timezone=True), nullable=True)

    __table_args__ = (
        db.UniqueConstraint('restaurant_id', 'email', name='uq_user_restaurant_email'),
        db.Index('ix_user_restaurant_role', 'restaurant_id', 'role'),
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def set_pin(self, pin):
        self.pin_hash = generate_password_hash(pin) if pin else None

    def check_pin(self, pin):
        if not self.pin_hash or not pin:
            return False
        return check_password_hash(self.pin_hash, pin)

    @property
    def is_owner(self):
        return self.role == 'owner'

    @property
    def is_manager(self):
        return self.role in ('owner', 'manager')

    @property
    def is_cashier(self):
        return self.role in ('owner', 'manager', 'cashier')

    @property
    def is_kitchen(self):
        return self.role == 'kitchen'

    def has_role(self, *roles):
        return self.role in roles

    def __repr__(self):
        return f"<User {self.id}: {self.email} ({self.role}) - Rest {self.restaurant_id}>"

