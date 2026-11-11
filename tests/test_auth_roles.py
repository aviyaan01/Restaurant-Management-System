import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from datetime import datetime, timezone, timedelta
from app import create_app
from app.extensions import db
from app.models.restaurant import Restaurant
from app.models.user import User
from app.models.audit import AuditLog

class TestConfig:
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = False  # Disabled strictly in test runner for direct form posting
    SECRET_KEY = 'test-secret-key'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)

def test_full_auth_and_role_workflow():
    app = create_app(TestConfig)
    client = app.test_client()

    with app.app_context():
        db.create_all()

        # 1. Seed Restaurant
        restaurant = Restaurant(
            name="Dhaka Biryani House",
            phone="01711223344",
            address="Dhanmondi, Dhaka",
            bin="001234567-0101",
            vat_rate=5.00,
            price_mode="exclusive"
        )
        db.session.add(restaurant)
        db.session.flush()

        # 2. Seed All 4 Roles
        owner = User(restaurant_id=restaurant.id, name="Owner Karim", email="owner@dhaka.local", phone="01711111111", role="owner", is_active=True)
        owner.set_password("ownerPass123")

        manager = User(restaurant_id=restaurant.id, name="Manager Rahim", email="manager@dhaka.local", phone="01722222222", role="manager", is_active=True)
        manager.set_password("managerPass123")

        cashier = User(restaurant_id=restaurant.id, name="Cashier Hasan", email="cashier@dhaka.local", phone="01733333333", role="cashier", is_active=True)
        cashier.set_password("cashierPass123")

        kitchen = User(restaurant_id=restaurant.id, name="Chef Baburchi", email="kitchen@dhaka.local", phone="01744444444", role="kitchen", is_active=True)
        kitchen.set_password("kitchenPass123")

        db.session.add_all([owner, manager, cashier, kitchen])
        db.session.commit()

        # TEST A: Wrong password & lockout counter
        res = client.post('/auth/login', data={'identifier': 'owner@dhaka.local', 'password': 'WrongPassword123'}, follow_redirects=True)
        assert b"Invalid credentials" in res.data
        u = db.session.get(User, owner.id)
        assert u.failed_login_count == 1
        assert u.locked_until is None

        # Trigger 4 more failures to reach 5
        for _ in range(4):
            client.post('/auth/login', data={'identifier': 'owner@dhaka.local', 'password': 'WrongPassword123'}, follow_redirects=True)
        db.session.refresh(u)
        assert u.failed_login_count == 5
        assert u.locked_until is not None
        locked_until = u.locked_until
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        assert locked_until > datetime.now(timezone.utc)
        print("✓ Account lockout after 5 consecutive failures verified.")

        # Locked account rejects even correct password
        res = client.post('/auth/login', data={'identifier': 'owner@dhaka.local', 'password': 'ownerPass123'}, follow_redirects=True)
        assert b"Account temporarily locked" in res.data or b"temporarily locked" in res.data
        print("✓ Locked account blocks correct password during lockout period.")

        # Reset lockout manually for testing successful flow
        u.failed_login_count = 0
        u.locked_until = None
        db.session.commit()

        # TEST B: Owner login and redirect to Admin Dashboard
        res = client.post('/auth/login', data={'identifier': 'owner@dhaka.local', 'password': 'ownerPass123'})
        assert res.status_code == 302
        assert res.location == '/admin/'
        print("✓ Owner redirect to /admin/ verified.")

        # Owner accesses owner-only settings
        res = client.get('/admin/owner-only')
        assert res.status_code == 200
        assert b"Owner Only Area" in res.data
        print("✓ Owner can access /admin/owner-only.")

        # Logout
        client.get('/auth/logout')

        # TEST C: Phone number login support
        res = client.post('/auth/login', data={'identifier': '01722222222', 'password': 'managerPass123'})
        assert res.status_code == 302
        assert res.location == '/admin/'
        print("✓ Manager login using phone number (01722222222) verified.")

        # TEST D: Manager opening owner-only route returns 403 Forbidden
        res = client.get('/admin/owner-only')
        assert res.status_code == 403
        assert b"403" in res.data
        print("✓ Manager opening /admin/owner-only returns 403 Forbidden on the server.")

        client.get('/auth/logout')

        # TEST E: Cashier login and redirect to POS
        res = client.post('/auth/login', data={'identifier': 'cashier@dhaka.local', 'password': 'cashierPass123'})
        assert res.status_code == 302
        assert res.location == '/pos/'
        print("✓ Cashier redirect to /pos/ verified.")

        # Cashier accessing /admin/ returns 403 Forbidden
        res = client.get('/admin/')
        assert res.status_code == 403
        print("✓ Cashier accessing /admin/ returns 403 Forbidden.")

        client.get('/auth/logout')

        # TEST F: Kitchen login and redirect to Kitchen Display
        res = client.post('/auth/login', data={'identifier': 'kitchen@dhaka.local', 'password': 'kitchenPass123'})
        assert res.status_code == 302
        assert res.location == '/kitchen/'
        print("✓ Kitchen staff redirect to /kitchen/ verified.")

        # Kitchen accessing /pos/ returns 403 Forbidden
        res = client.get('/pos/')
        assert res.status_code == 403
        print("✓ Kitchen staff accessing /pos/ returns 403 Forbidden.")

        # TEST G: Deactivated user immediate block via before_request
        k_user = db.session.get(User, kitchen.id)
        k_user.is_active = False
        db.session.commit()

        # Active session makes request after deactivation
        res = client.get('/kitchen/', follow_redirects=True)
        assert b"deactivated" in res.data
        print("✓ Deactivated user immediately kicked out by before_request.")

        # Audit log entries recorded
        audit_count = AuditLog.query.count()
        assert audit_count > 0
        print(f"✓ Total audit log entries recorded during tests: {audit_count}.")

if __name__ == '__main__':
    test_full_auth_and_role_workflow()
    print("\nALL STEP 3 REQUIREMENTS PASSED PERFECTLY!")
