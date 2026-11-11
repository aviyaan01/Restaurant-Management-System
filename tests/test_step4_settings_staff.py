import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from app import create_app
from app.extensions import db
from app.models.restaurant import Restaurant
from app.models.user import User
from app.models.audit import AuditLog

class TestConfig:
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = False  # Disabled strictly in test client for direct POST testing
    SECRET_KEY = 'test-secret-key-step4'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)

def test_step4_settings_and_staff():
    app = create_app(TestConfig)
    client = app.test_client()

    with app.app_context():
        db.create_all()

        # 1. Setup Test Restaurant
        restaurant = Restaurant(
            name="Sultan's Feast",
            phone="01700000001",
            address="Gulshan 2, Dhaka",
            bin="001122334-0101",
            vat_rate=Decimal("5.00"),
            price_mode="exclusive",
            receipt_footer="ধন্যবাদ, আবার আসবেন!"
        )
        db.session.add(restaurant)
        db.session.flush()

        # 2. Setup Primary Owner and Manager
        owner = User(
            restaurant_id=restaurant.id,
            name="Principal Owner",
            email="owner@feast.com",
            phone="01711111111",
            role="owner",
            is_active=True
        )
        owner.set_password("ownerPass123")

        manager = User(
            restaurant_id=restaurant.id,
            name="Floor Manager",
            email="manager@feast.com",
            phone="01722222222",
            role="manager",
            is_active=True
        )
        manager.set_password("managerPass123")

        db.session.add_all([owner, manager])
        db.session.commit()

        # ----------------------------------------------------------------------
        # TEST 1: Manager accessing settings or staff receives 403 Forbidden
        # ----------------------------------------------------------------------
        client.post('/auth/login', data={'identifier': 'manager@feast.com', 'password': 'managerPass123'})
        
        res = client.get('/admin/settings')
        assert res.status_code == 403, f"Expected 403 for Manager accessing /admin/settings, got {res.status_code}"
        assert b"403" in res.data

        res = client.get('/admin/staff')
        assert res.status_code == 403, f"Expected 403 for Manager accessing /admin/staff, got {res.status_code}"
        assert b"403" in res.data
        print("✓ Non-negotiable Rule 2 passed: Manager blocked with 403 Forbidden on both Settings and Staff.")

        client.get('/auth/logout')

        # ----------------------------------------------------------------------
        # TEST 2: Owner updates settings and audit log is written
        # ----------------------------------------------------------------------
        client.post('/auth/login', data={'identifier': 'owner@feast.com', 'password': 'ownerPass123'})
        
        res = client.get('/admin/settings')
        assert res.status_code == 200
        assert b"Restaurant Profile" in res.data

        # Post updated settings
        res = client.post('/admin/settings', data={
            'name': "Sultan's Grand Dine",
            'phone': '01799999999',
            'address': 'Banani 11, Dhaka',
            'bin': '998877665-0101',
            'vat_rate': '7.50',
            'price_mode': 'inclusive',
            'receipt_footer': 'Thank you! Visit again!'
        }, follow_redirects=True)
        assert res.status_code == 200
        assert b"updated successfully" in res.data

        # Verify DB updated
        db.session.refresh(restaurant)
        assert restaurant.name == "Sultan's Grand Dine"
        assert restaurant.phone == "01799999999"
        assert restaurant.bin == "998877665-0101"
        assert restaurant.vat_rate == Decimal("7.50")
        assert restaurant.price_mode == "inclusive"
        assert restaurant.receipt_footer == "Thank you! Visit again!"

        # Verify Audit Log entry
        settings_audit = AuditLog.query.filter_by(
            action='SETTINGS_UPDATED',
            record_type='Restaurant',
            record_id=restaurant.id
        ).first()
        assert settings_audit is not None
        assert settings_audit.details['new']['name'] == "Sultan's Grand Dine"
        print("✓ Owner settings update & Rule 5 AuditLog verification passed.")

        # ----------------------------------------------------------------------
        # TEST 3: Staff Creation & Tenant Email Uniqueness
        # ----------------------------------------------------------------------
        # Add Cashier
        res = client.post('/admin/staff/new', data={
            'name': 'Cashier Habib',
            'email': 'cashier.habib@feast.com',
            'phone': '01733333333',
            'role': 'cashier',
            'password': 'habibPassword123'
        }, follow_redirects=True)
        assert res.status_code == 200
        assert b"Cashier Habib" in res.data

        new_cashier = User.query.filter_by(email='cashier.habib@feast.com').first()
        assert new_cashier is not None
        assert new_cashier.role == 'cashier'
        assert new_cashier.is_active is True
        assert new_cashier.restaurant_id == restaurant.id

        # Verify Audit Log
        staff_audit = AuditLog.query.filter_by(action='STAFF_CREATED', record_id=new_cashier.id).first()
        assert staff_audit is not None
        assert staff_audit.details['role'] == 'cashier'
        print("✓ Staff creation and audit logging passed.")

        # Duplicate email in same restaurant rejected
        res = client.post('/admin/staff/new', data={
            'name': 'Duplicate Person',
            'email': 'cashier.habib@feast.com',
            'role': 'cashier',
            'password': 'password123'
        })
        assert b"already exists" in res.data
        print("✓ Tenant-scoped email collision rejection passed.")

        # ----------------------------------------------------------------------
        # TEST 4: Search & Pagination
        # ----------------------------------------------------------------------
        res = client.get('/admin/staff?q=Habib')
        assert b"Cashier Habib" in res.data
        assert b"Floor Manager" not in res.data

        res = client.get('/admin/staff?q=01722222222')
        assert b"Floor Manager" in res.data
        assert b"Cashier Habib" not in res.data
        print("✓ Staff search filter (name and phone) passed.")

        # ----------------------------------------------------------------------
        # TEST 5: Active/Inactive Toggle via HTMX
        # ----------------------------------------------------------------------
        res = client.post(
            f'/admin/staff/{new_cashier.id}/toggle-status',
            headers={'HX-Request': 'true'}
        )
        assert res.status_code == 200
        db.session.refresh(new_cashier)
        assert new_cashier.is_active is False
        assert b"Inactive" in res.data
        assert b"Activate" in res.data

        # Toggle back to active
        res = client.post(
            f'/admin/staff/{new_cashier.id}/toggle-status',
            headers={'HX-Request': 'true'}
        )
        assert res.status_code == 200
        db.session.refresh(new_cashier)
        assert new_cashier.is_active is True
        print("✓ HTMX instant staff active/deactive toggle passed.")

        # ----------------------------------------------------------------------
        # TEST 6: Invariant: Last active owner cannot deactivate or demote themselves
        # ----------------------------------------------------------------------
        # Try deactivating primary owner (who is currently the only active owner)
        res = client.post(
            f'/admin/staff/{owner.id}/toggle-status',
            headers={'HX-Request': 'true'}
        )
        assert res.status_code == 400
        assert b"Cannot deactivate the last active owner" in res.data
        db.session.refresh(owner)
        assert owner.is_active is True
        print("✓ Invariant passed: Last active owner cannot deactivate themselves via toggle.")

        # Try demoting owner to manager via edit form
        res = client.post(f'/admin/staff/{owner.id}/edit', data={
            'name': 'Principal Owner',
            'email': 'owner@feast.com',
            'phone': '01711111111',
            'role': 'manager',
            'is_active': 'y'
        })
        assert b"Cannot demote the last active owner" in res.data
        db.session.refresh(owner)
        assert owner.role == 'owner'
        print("✓ Invariant passed: Last active owner cannot demote themselves via edit form.")

        # Add a secondary active co-owner
        co_owner = User(
            restaurant_id=restaurant.id,
            name="Second Owner",
            email="owner2@feast.com",
            role="owner",
            is_active=True
        )
        co_owner.set_password("coOwnerPass123")
        db.session.add(co_owner)
        db.session.commit()

        # Now that 2 active owners exist, one CAN be deactivated
        res = client.post(
            f'/admin/staff/{co_owner.id}/toggle-status',
            headers={'HX-Request': 'true'}
        )
        assert res.status_code == 200
        db.session.refresh(co_owner)
        assert co_owner.is_active is False
        print("✓ Co-owner deactivation allowed when another active owner remains.")

if __name__ == '__main__':
    test_step4_settings_and_staff()
    print("\nALL STEP 4 SPECIFICATIONS AND INVARIANTS PASSED PERFECTLY!")
