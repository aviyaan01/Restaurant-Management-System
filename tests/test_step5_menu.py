import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import unittest
from datetime import timedelta
from decimal import Decimal
from app import create_app
from app.extensions import db
from app.models.restaurant import Restaurant
from app.models.user import User
from app.models.menu import Category, Dish
from app.models.order import Order, OrderItem
from app.models.audit import AuditLog

class TestConfig:
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = False
    SECRET_KEY = 'test-secret-key-step-5'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)

class Step5MenuManagementTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

        # Seed Restaurant
        self.restaurant = Restaurant(
            name="Grand Nawab",
            phone="01710000000",
            address="Old Dhaka",
            bin="112233445-0101",
            vat_rate=Decimal("5.00"),
            price_mode="exclusive"
        )
        db.session.add(self.restaurant)
        db.session.commit()

        # Seed Users: Owner, Manager, Cashier, Kitchen
        self.owner = User(
            restaurant_id=self.restaurant.id,
            name="Nawab Owner",
            email="owner@nawab.com",
            phone="01710000001",
            role="owner",
            is_active=True
        )
        self.owner.set_password("ownerPassword123")

        self.manager = User(
            restaurant_id=self.restaurant.id,
            name="Nawab Manager",
            email="manager@nawab.com",
            phone="01710000002",
            role="manager",
            is_active=True
        )
        self.manager.set_password("managerPassword123")

        self.cashier = User(
            restaurant_id=self.restaurant.id,
            name="Nawab Cashier",
            email="cashier@nawab.com",
            phone="01710000003",
            role="cashier",
            is_active=True
        )
        self.cashier.set_password("cashierPassword123")

        self.kitchen = User(
            restaurant_id=self.restaurant.id,
            name="Nawab Kitchen",
            email="kitchen@nawab.com",
            phone="01710000004",
            role="kitchen",
            is_active=True
        )
        self.kitchen.set_password("kitchenPassword123")

        db.session.add_all([self.owner, self.manager, self.cashier, self.kitchen])
        db.session.commit()

        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def login(self, email, password):
        return self.client.post('/auth/login', data={
            'identifier': email,
            'password': password
        }, follow_redirects=True)

    def test_role_gating_for_menu(self):
        """Owner and Manager can access menu routes; Cashier and Kitchen are blocked with 403."""
        # 1. Owner access
        self.client.get('/auth/logout')
        self.login('owner@nawab.com', 'ownerPassword123')
        r1 = self.client.get('/admin/categories')
        self.assertEqual(r1.status_code, 200)
        r2 = self.client.get('/admin/dishes')
        self.assertEqual(r2.status_code, 200)

        # 2. Manager access
        self.client.get('/auth/logout')
        self.login('manager@nawab.com', 'managerPassword123')
        r3 = self.client.get('/admin/categories')
        self.assertEqual(r3.status_code, 200)
        r4 = self.client.get('/admin/dishes')
        self.assertEqual(r4.status_code, 200)

        # 3. Cashier blocked
        self.client.get('/auth/logout')
        self.login('cashier@nawab.com', 'cashierPassword123')
        r5 = self.client.get('/admin/categories')
        self.assertEqual(r5.status_code, 403)
        r6 = self.client.get('/admin/dishes')
        self.assertEqual(r6.status_code, 403)

        # 4. Kitchen staff blocked
        self.client.get('/auth/logout')
        self.login('kitchen@nawab.com', 'kitchenPassword123')
        r7 = self.client.get('/admin/categories')
        self.assertEqual(r7.status_code, 403)
        r8 = self.client.get('/admin/dishes')
        self.assertEqual(r8.status_code, 403)
        print("✓ Non-negotiable Rule 2 passed: Only Owner & Manager can access Category/Dish routes; Cashier & Kitchen receive 403.")

    def test_category_crud_and_safety_invariant(self):
        """Category creation, dish count display, and deletion restriction with active dishes."""
        self.login('manager@nawab.com', 'managerPassword123')

        # 1. Create Category
        resp = self.client.post('/admin/categories/new', data={
            'name': 'Biryani',
            'sort_order': 1
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        cat = Category.query.filter_by(name='Biryani', restaurant_id=self.restaurant.id).first()
        self.assertIsNotNone(cat)
        self.assertEqual(cat.sort_order, 1)

        # Verify AuditLog
        log_cat = AuditLog.query.filter_by(action='CATEGORY_CREATED', record_id=cat.id).first()
        self.assertIsNotNone(log_cat)

        # 2. Add an active dish to this category
        dish = Dish(
            restaurant_id=self.restaurant.id,
            category_id=cat.id,
            name="Kacchi Biryani",
            price=Decimal("450.00"),
            discount=Decimal("0.00"),
            veg_type="non_veg",
            prep_time_minutes=20,
            is_available=True,
            is_archived=False
        )
        db.session.add(dish)
        db.session.commit()

        # 3. Verify category page shows dish count
        resp_list = self.client.get('/admin/categories')
        self.assertIn(b"1 dish", resp_list.data)

        # 4. Attempt to delete category that contains active dishes -> MUST FAIL
        resp_del = self.client.post(f'/admin/categories/{cat.id}/delete', follow_redirects=True)
        self.assertIn(b"Cannot delete category", resp_del.data)
        cat_still_exists = db.session.get(Category, cat.id)
        self.assertIsNotNone(cat_still_exists)
        print("✓ Safety Invariant passed: Category with active dishes cannot be deleted.")

        # 5. Archive or delete dish, then category deletion succeeds
        dish.is_archived = True
        db.session.commit()

        resp_del_success = self.client.post(f'/admin/categories/{cat.id}/delete', follow_redirects=True)
        self.assertIn(b"deleted successfully", resp_del_success.data)
        cat_deleted = db.session.get(Category, cat.id)
        self.assertIsNone(cat_deleted)
        print("✓ Category deleted successfully once emptied of active dishes.")

    def test_dish_validation_negative_price_and_discount(self):
        """Rule 4: Reject negative price and discount greater than price on server."""
        self.login('manager@nawab.com', 'managerPassword123')

        cat = Category(restaurant_id=self.restaurant.id, name="Beverages", sort_order=2)
        db.session.add(cat)
        db.session.commit()

        # 1. Attempt negative price
        resp_neg_price = self.client.post('/admin/dishes/new', data={
            'name': 'Cold Drink',
            'category_id': cat.id,
            'price': '-50.00',
            'discount': '0.00',
            'veg_type': 'veg',
            'prep_time_minutes': 5,
            'is_available': 'y'
        })
        self.assertIn(b"Price cannot be negative", resp_neg_price.data)
        self.assertEqual(Dish.query.filter_by(name='Cold Drink').count(), 0)
        print("✓ Rule 4 passed: Server-side validation rejected negative price.")

        # 2. Attempt discount greater than price
        resp_high_discount = self.client.post('/admin/dishes/new', data={
            'name': 'Cold Drink',
            'category_id': cat.id,
            'price': '40.00',
            'discount': '50.00',  # 50 > 40
            'veg_type': 'veg',
            'prep_time_minutes': 5,
            'is_available': 'y'
        })
        self.assertIn(b"Discount (\xe0\xa7\xb3) cannot be greater than the regular price", resp_high_discount.data)
        self.assertEqual(Dish.query.filter_by(name='Cold Drink').count(), 0)
        print("✓ Rule 4 passed: Server-side validation rejected discount greater than price.")

    def test_dish_crud_and_price_change_audit_log(self):
        """Rule 3 & 5: Dish CRUD with BDT Numeric and price change logged to AuditLog."""
        self.login('owner@nawab.com', 'ownerPassword123')

        cat = Category(restaurant_id=self.restaurant.id, name="Dessert", sort_order=3)
        db.session.add(cat)
        db.session.commit()

        # 1. Create Dish
        resp_create = self.client.post('/admin/dishes/new', data={
            'name': 'Shahi Firni',
            'category_id': cat.id,
            'price': '120.00',
            'discount': '10.00',
            'veg_type': 'veg',
            'prep_time_minutes': 10,
            'is_available': 'y'
        }, follow_redirects=True)
        self.assertEqual(resp_create.status_code, 200)

        dish = Dish.query.filter_by(name='Shahi Firni').first()
        self.assertIsNotNone(dish)
        self.assertEqual(dish.price, Decimal('120.00'))
        self.assertEqual(dish.discount, Decimal('10.00'))

        # Verify Dish Created audit entry
        log_create = AuditLog.query.filter_by(action='DISH_CREATED', record_id=dish.id).first()
        self.assertIsNotNone(log_create)
        print("✓ Dish created and initial creation logged to AuditLog.")

        # 2. Edit Dish Price: change price from 120.00 to 140.00 and discount to 0.00
        resp_edit = self.client.post(f'/admin/dishes/{dish.id}/edit', data={
            'name': 'Shahi Firni (Special)',
            'category_id': cat.id,
            'price': '140.00',
            'discount': '0.00',
            'veg_type': 'veg',
            'prep_time_minutes': 10,
            'is_available': 'y'
        }, follow_redirects=True)
        self.assertEqual(resp_edit.status_code, 200)

        dish_updated = db.session.get(Dish, dish.id)
        self.assertEqual(dish_updated.price, Decimal('140.00'))
        self.assertEqual(dish_updated.discount, Decimal('0.00'))

        # Rule 5: Verify DISH_PRICE_CHANGED in AuditLog
        log_price = AuditLog.query.filter_by(action='DISH_PRICE_CHANGED', record_id=dish.id).first()
        self.assertIsNotNone(log_price)
        self.assertEqual(log_price.user_id, self.owner.id)
        self.assertEqual(log_price.details['old_price'], 120.0)
        self.assertEqual(log_price.details['new_price'], 140.0)
        print("✓ Rule 5 passed: Price change recorded to AuditLog with old & new amounts.")

    def test_dish_htmx_availability_toggle(self):
        """HTMX toggle updates is_available instantly in-place."""
        self.login('manager@nawab.com', 'managerPassword123')

        cat = Category(restaurant_id=self.restaurant.id, name="Starters", sort_order=1)
        dish = Dish(
            restaurant_id=self.restaurant.id,
            category_id=cat.id,
            name="Chicken Tikka",
            price=Decimal("280.00"),
            is_available=True
        )
        db.session.add_all([cat, dish])
        db.session.commit()

        # Toggle to out of stock
        resp = self.client.post(
            f'/admin/dishes/{dish.id}/toggle-available',
            headers={'HX-Request': 'true'}
        )
        self.assertEqual(resp.status_code, 200)
        dish_db = db.session.get(Dish, dish.id)
        self.assertFalse(dish_db.is_available)
        self.assertIn(b"Out of Stock", resp.data)
        self.assertIn(b"Set In Stock", resp.data)

        # Toggle back to available
        resp2 = self.client.post(
            f'/admin/dishes/{dish.id}/toggle-available',
            headers={'HX-Request': 'true'}
        )
        self.assertEqual(resp2.status_code, 200)
        dish_db2 = db.session.get(Dish, dish.id)
        self.assertTrue(dish_db2.is_available)
        self.assertIn(b"Available", resp2.data)
        print("✓ HTMX instant availability toggle passed.")

    def test_soft_archiving_for_ordered_dishes_vs_hard_deletion(self):
        """A dish used in past orders is archived (is_archived=True), while an unused dish is hard-deleted."""
        self.login('manager@nawab.com', 'managerPassword123')

        cat = Category(restaurant_id=self.restaurant.id, name="Platters", sort_order=1)
        dish_used = Dish(
            restaurant_id=self.restaurant.id,
            category_id=cat.id,
            name="Nawab Platter Special",
            price=Decimal("950.00"),
            is_available=True
        )
        dish_unused = Dish(
            restaurant_id=self.restaurant.id,
            category_id=cat.id,
            name="Seasonal Fruit Bowl",
            price=Decimal("150.00"),
            is_available=True
        )
        db.session.add_all([cat, dish_used, dish_unused])
        db.session.commit()

        # Simulate a past order that contains dish_used
        order = Order(
            restaurant_id=self.restaurant.id,
            order_no=101,
            type="dine_in",
            status="paid",
            subtotal=Decimal("950.00"),
            total=Decimal("997.50")
        )
        db.session.add(order)
        db.session.commit()

        order_item = OrderItem(
            restaurant_id=self.restaurant.id,
            order_id=order.id,
            dish_id=dish_used.id,
            dish_name_snapshot=dish_used.name,
            unit_price_snapshot=dish_used.price,
            quantity=1
        )
        db.session.add(order_item)
        db.session.commit()

        # 1. Attempt to delete dish_used -> MUST BE ARCHIVED, NOT DELETED
        resp_del_used = self.client.post(f'/admin/dishes/{dish_used.id}/delete', follow_redirects=True)
        self.assertIn(b"has been ordered previously, so it cannot be hard-deleted", resp_del_used.data)

        dish_used_db = db.session.get(Dish, dish_used.id)
        self.assertIsNotNone(dish_used_db)
        self.assertTrue(dish_used_db.is_archived)
        self.assertFalse(dish_used_db.is_available)

        # AuditLog check
        log_archive = AuditLog.query.filter_by(action='DISH_ARCHIVED', record_id=dish_used.id).first()
        self.assertIsNotNone(log_archive)
        print("✓ Invariant passed: Dish referenced in past orders was soft-archived, protecting order integrity.")

        # 2. Attempt to delete dish_unused -> Hard deletion allowed
        unused_id = dish_unused.id
        resp_del_unused = self.client.post(f'/admin/dishes/{dish_unused.id}/delete', follow_redirects=True)
        self.assertIn(b"deleted permanently", resp_del_unused.data)

        dish_unused_db = db.session.get(Dish, unused_id)
        self.assertIsNone(dish_unused_db)
        print("✓ Unused dish was hard-deleted cleanly.")

    def test_dish_search_and_category_filter(self):
        """Dish search query and category filtering work correctly."""
        self.login('manager@nawab.com', 'managerPassword123')

        c1 = Category(restaurant_id=self.restaurant.id, name="Rice", sort_order=1)
        c2 = Category(restaurant_id=self.restaurant.id, name="Bread", sort_order=2)
        db.session.add_all([c1, c2])
        db.session.commit()

        d1 = Dish(restaurant_id=self.restaurant.id, category_id=c1.id, name="Basmati Rice", price=Decimal("100.00"))
        d2 = Dish(restaurant_id=self.restaurant.id, category_id=c2.id, name="Garlic Naan", price=Decimal("60.00"))
        db.session.add_all([d1, d2])
        db.session.commit()

        # Search by name
        r_search = self.client.get('/admin/dishes?q=Basmati')
        self.assertIn(b"Basmati Rice", r_search.data)
        self.assertNotIn(b"Garlic Naan", r_search.data)

        # Filter by category
        r_cat = self.client.get(f'/admin/dishes?category_id={c2.id}')
        self.assertIn(b"Garlic Naan", r_cat.data)
        self.assertNotIn(b"Basmati Rice", r_cat.data)
        print("✓ Dish search filter and category filter passed.")

if __name__ == '__main__':
    unittest.main()
