import os
import sys

# Prevent Windows Application Control DLL load issues for C extensions
os.environ.setdefault("DISABLE_SQLALCHEMY_CEXT", "1")

import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal

# Ensure project root in python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app import create_app
from app.extensions import db
from app.models.restaurant import Restaurant
from app.models.user import User
from app.models.menu import Category, Dish
from app.models.table import Space, Table
from app.models.order import Order, OrderItem
from app.models.payment import Payment
from app.models.finance import FinanceEntry
from app.models.audit import AuditLog
from app.services.billing_service import calculate_bill

def seed_database(reset=False):
    """
    Populates the database with realistic multi-tenant demonstration data:
    - 2 Independent Restaurant Tenants (Kacchi Bhai & Sultan's Feast)
    - Complete Staff Accounts across all 4 Roles (Owner, Manager, Cashier, Kitchen Chef)
    - Dining Spaces and Tables with live occupancy states
    - Categorized Menus with BDT prices and discounts
    - Active Kitchen Tickets (for KDS testing)
    - Completed & Paid Orders (with Cash & bKash split payments)
    - Daily Purchases and Operating Expenses (for Finance Cashbook testing)
    - Audit Logs capturing historical security events
    """
    app = create_app()

    with app.app_context():
        if reset:
            print("Resetting database tables (--reset flag provided)...")
            db.drop_all()
            db.create_all()
        else:
            db.create_all()
            if Restaurant.query.first():
                print("Database already contains data.")
                print("Use 'python seed_demo.py --reset' to clear and re-seed clean demonstration data.")
                return

        now_utc = datetime.now(timezone.utc)
        yesterday_dt = now_utc - timedelta(days=1)

        print("\n" + "="*60)
        print("  BanglaPOS: Seeding Rich Multi-Tenant Demonstration Data")
        print("="*60 + "\n")

        # ======================================================================
        # TENANT 1: Kacchi Bhai (Banani) - Primary Restaurant
        # ======================================================================
        print("Creating Tenant 1: Kacchi Bhai (Banani)...")
        rest1 = Restaurant(
            name="Kacchi Bhai (Banani)",
            phone="01711223344",
            address="Road 11, Block D, Banani, Dhaka-1213",
            bin="123456789-0101",
            vat_rate=Decimal("5.00"),
            price_mode="exclusive",
            receipt_footer="ধন্যবাদ, আবার আসবেন! Powered by BanglaPOS"
        )
        db.session.add(rest1)
        db.session.flush()

        # Staff for Tenant 1
        owner1 = User(
            restaurant_id=rest1.id,
            name="Karim Owner",
            email="owner@kacchi.com",
            phone="01711223301",
            role="owner",
            is_active=True
        )
        owner1.set_password("owner123")

        manager1 = User(
            restaurant_id=rest1.id,
            name="Rahim Manager",
            email="manager@kacchi.com",
            phone="01711223302",
            role="manager",
            is_active=True
        )
        manager1.set_password("manager123")

        cashier1 = User(
            restaurant_id=rest1.id,
            name="Habib Cashier",
            email="cashier@kacchi.com",
            phone="01711223303",
            role="cashier",
            is_active=True
        )
        cashier1.set_password("cashier123")

        kitchen1 = User(
            restaurant_id=rest1.id,
            name="Chef Rafiq",
            email="kitchen@kacchi.com",
            phone="01711223304",
            role="kitchen",
            is_active=True
        )
        kitchen1.set_password("kitchen123")

        db.session.add_all([owner1, manager1, cashier1, kitchen1])
        db.session.flush()

        # Spaces & Tables for Tenant 1
        sp_ground = Space(restaurant_id=rest1.id, name="Ground Floor")
        sp_ac = Space(restaurant_id=rest1.id, name="AC Dining Hall")
        db.session.add_all([sp_ground, sp_ac])
        db.session.flush()

        t_01 = Table(restaurant_id=rest1.id, space_id=sp_ground.id, name="T-01", capacity=4, cover_charge=Decimal("0.00"), status="occupied")
        t_02 = Table(restaurant_id=rest1.id, space_id=sp_ground.id, name="T-02", capacity=4, cover_charge=Decimal("0.00"), status="open")
        t_03 = Table(restaurant_id=rest1.id, space_id=sp_ground.id, name="T-03", capacity=2, cover_charge=Decimal("0.00"), status="open")
        t_04 = Table(restaurant_id=rest1.id, space_id=sp_ground.id, name="T-04", capacity=6, cover_charge=Decimal("0.00"), status="open")
        t_ac1 = Table(restaurant_id=rest1.id, space_id=sp_ac.id, name="AC-1", capacity=4, cover_charge=Decimal("50.00"), status="open")
        t_ac2 = Table(restaurant_id=rest1.id, space_id=sp_ac.id, name="AC-2", capacity=4, cover_charge=Decimal("50.00"), status="open")
        db.session.add_all([t_01, t_02, t_03, t_04, t_ac1, t_ac2])

        # Categories & Dishes for Tenant 1
        cat_biryani = Category(restaurant_id=rest1.id, name="Biryani and Mains", sort_order=1)
        cat_sides = Category(restaurant_id=rest1.id, name="Sides and Desserts", sort_order=2)
        cat_drinks = Category(restaurant_id=rest1.id, name="Beverages", sort_order=3)
        db.session.add_all([cat_biryani, cat_sides, cat_drinks])
        db.session.flush()

        d_kacchi = Dish(restaurant_id=rest1.id, category_id=cat_biryani.id, name="Basmati Mutton Kacchi", price=Decimal("480.00"), discount=Decimal("0.00"), veg_type="non_veg", prep_time_minutes=15, is_available=True)
        d_polao = Dish(restaurant_id=rest1.id, category_id=cat_biryani.id, name="Chicken Roast Polao", price=Decimal("350.00"), discount=Decimal("0.00"), veg_type="non_veg", prep_time_minutes=12, is_available=True)
        d_tehari = Dish(restaurant_id=rest1.id, category_id=cat_biryani.id, name="Beef Tehari (Old Dhaka)", price=Decimal("320.00"), discount=Decimal("20.00"), veg_type="non_veg", prep_time_minutes=10, is_available=True)
        d_borhani = Dish(restaurant_id=rest1.id, category_id=cat_sides.id, name="Special Borhani (250ml)", price=Decimal("80.00"), discount=Decimal("10.00"), veg_type="veg", prep_time_minutes=2, is_available=True)
        d_firni = Dish(restaurant_id=rest1.id, category_id=cat_sides.id, name="Shahi Jafrani Firni", price=Decimal("120.00"), discount=Decimal("0.00"), veg_type="veg", prep_time_minutes=5, is_available=True)
        d_soda = Dish(restaurant_id=rest1.id, category_id=cat_drinks.id, name="Fresh Lime Soda", price=Decimal("60.00"), discount=Decimal("0.00"), veg_type="veg", prep_time_minutes=3, is_available=True)
        d_water = Dish(restaurant_id=rest1.id, category_id=cat_drinks.id, name="Mineral Water 500ml", price=Decimal("25.00"), discount=Decimal("0.00"), veg_type="veg", prep_time_minutes=1, is_available=True)
        db.session.add_all([d_kacchi, d_polao, d_tehari, d_borhani, d_firni, d_soda, d_water])
        db.session.flush()

        # ----------------------------------------------------------------------
        # Realistic Orders for Tenant 1
        # ----------------------------------------------------------------------
        # Order 1: Active Dine-in on Table T-01 (Shows on KDS as 'preparing' & Table Board as Occupied)
        bill1 = calculate_bill(subtotal=Decimal("1100.00"), discount_type="flat", discount_value=Decimal("20.00"), cover_charge=Decimal("0.00"), vat_rate=Decimal("5.00"), price_mode="exclusive")
        order1 = Order(
            restaurant_id=rest1.id,
            order_no=1,
            type="dine_in",
            table_id=t_01.id,
            status="open",
            payment_status="unpaid",
            subtotal=bill1['subtotal'],
            discount=bill1['discount'],
            cover_charge=bill1['cover_charge'],
            vat_amount=bill1['vat_amount'],
            total=bill1['total'],
            created_by=cashier1.id,
            created_at=now_utc - timedelta(minutes=14)
        )
        db.session.add(order1)
        db.session.flush()

        oi1_1 = OrderItem(
            restaurant_id=rest1.id,
            order_id=order1.id,
            dish_id=d_kacchi.id,
            dish_name_snapshot="Basmati Mutton Kacchi",
            unit_price_snapshot=Decimal("480.00"),
            quantity=2,
            note="Extra aloo please",
            kitchen_status="preparing",
            created_at=now_utc - timedelta(minutes=14)
        )
        oi1_2 = OrderItem(
            restaurant_id=rest1.id,
            order_id=order1.id,
            dish_id=d_borhani.id,
            dish_name_snapshot="Special Borhani (250ml)",
            unit_price_snapshot=Decimal("70.00"),
            quantity=2,
            note="Chilled",
            kitchen_status="new",
            created_at=now_utc - timedelta(minutes=14)
        )
        db.session.add_all([oi1_1, oi1_2])

        # Order 2: Active Take-Away (Shows on KDS as 'new', wait time 5 mins)
        bill2 = calculate_bill(subtotal=Decimal("350.00"), discount_type="flat", discount_value=Decimal("0.00"), cover_charge=Decimal("0.00"), vat_rate=Decimal("5.00"), price_mode="exclusive")
        order2 = Order(
            restaurant_id=rest1.id,
            order_no=2,
            type="take_away",
            table_id=None,
            status="open",
            payment_status="unpaid",
            subtotal=bill2['subtotal'],
            discount=bill2['discount'],
            cover_charge=bill2['cover_charge'],
            vat_amount=bill2['vat_amount'],
            total=bill2['total'],
            created_by=cashier1.id,
            created_at=now_utc - timedelta(minutes=5)
        )
        db.session.add(order2)
        db.session.flush()

        oi2_1 = OrderItem(
            restaurant_id=rest1.id,
            order_id=order2.id,
            dish_id=d_polao.id,
            dish_name_snapshot="Chicken Roast Polao",
            unit_price_snapshot=Decimal("350.00"),
            quantity=1,
            note="Pack sauce separately",
            kitchen_status="new",
            created_at=now_utc - timedelta(minutes=5)
        )
        db.session.add(oi2_1)

        # Order 3: Completed & Paid Dine-In (Paid in Cash, change given, FinanceEntry created)
        bill3 = calculate_bill(subtotal=Decimal("960.00"), discount_type="flat", discount_value=Decimal("0.00"), cover_charge=Decimal("0.00"), vat_rate=Decimal("5.00"), price_mode="exclusive")
        order3 = Order(
            restaurant_id=rest1.id,
            order_no=3,
            type="dine_in",
            table_id=t_02.id,
            status="paid",
            payment_status="paid",
            subtotal=bill3['subtotal'],
            discount=bill3['discount'],
            cover_charge=bill3['cover_charge'],
            vat_amount=bill3['vat_amount'],
            total=bill3['total'],
            created_by=cashier1.id,
            paid_at=now_utc - timedelta(minutes=45),
            created_at=now_utc - timedelta(minutes=70)
        )
        db.session.add(order3)
        db.session.flush()

        oi3_1 = OrderItem(
            restaurant_id=rest1.id,
            order_id=order3.id,
            dish_id=d_kacchi.id,
            dish_name_snapshot="Basmati Mutton Kacchi",
            unit_price_snapshot=Decimal("480.00"),
            quantity=2,
            kitchen_status="ready",
            created_at=now_utc - timedelta(minutes=70)
        )
        pay3 = Payment(
            restaurant_id=rest1.id,
            order_id=order3.id,
            method="cash",
            amount=bill3['total'],
            status="completed",
            received_by=cashier1.id,
            created_at=now_utc - timedelta(minutes=45)
        )
        fe3 = FinanceEntry(
            restaurant_id=rest1.id,
            type="sale",
            amount=bill3['total'],
            note=f"POS Dine In Order #{order3.order_no} (Cash)",
            order_id=order3.id,
            created_by=cashier1.id,
            entry_date=now_utc - timedelta(minutes=45)
        )
        db.session.add_all([oi3_1, pay3, fe3])

        # Order 4: Completed Quick Billing (Paid via bKash)
        bill4 = calculate_bill(subtotal=Decimal("300.00"), discount_type="flat", discount_value=Decimal("0.00"), cover_charge=Decimal("0.00"), vat_rate=Decimal("5.00"), price_mode="exclusive")
        order4 = Order(
            restaurant_id=rest1.id,
            order_no=4,
            type="quick",
            table_id=None,
            status="paid",
            payment_status="paid",
            subtotal=bill4['subtotal'],
            discount=bill4['discount'],
            cover_charge=bill4['cover_charge'],
            vat_amount=bill4['vat_amount'],
            total=bill4['total'],
            created_by=cashier1.id,
            paid_at=now_utc - timedelta(minutes=30),
            created_at=now_utc - timedelta(minutes=32)
        )
        db.session.add(order4)
        db.session.flush()

        oi4_1 = OrderItem(
            restaurant_id=rest1.id,
            order_id=order4.id,
            dish_id=d_tehari.id,
            dish_name_snapshot="Beef Tehari (Old Dhaka)",
            unit_price_snapshot=Decimal("300.00"),
            quantity=1,
            kitchen_status="ready",
            created_at=now_utc - timedelta(minutes=32)
        )
        pay4 = Payment(
            restaurant_id=rest1.id,
            order_id=order4.id,
            method="bkash",
            amount=bill4['total'],
            reference="TRX88992211",
            status="completed",
            received_by=cashier1.id,
            created_at=now_utc - timedelta(minutes=30)
        )
        fe4 = FinanceEntry(
            restaurant_id=rest1.id,
            type="sale",
            amount=bill4['total'],
            note=f"POS Quick Billing Order #{order4.order_no} (bKash TRX88992211)",
            order_id=order4.id,
            created_by=cashier1.id,
            entry_date=now_utc - timedelta(minutes=30)
        )
        db.session.add_all([oi4_1, pay4, fe4])

        # Order 5: Cancelled Order with mandatory reason
        bill5 = calculate_bill(subtotal=Decimal("480.00"), discount_type="flat", discount_value=Decimal("0.00"), cover_charge=Decimal("0.00"), vat_rate=Decimal("5.00"), price_mode="exclusive")
        order5 = Order(
            restaurant_id=rest1.id,
            order_no=5,
            type="dine_in",
            table_id=t_03.id,
            status="cancelled",
            payment_status="unpaid",
            cancel_reason="Customer had an urgent call and left before dining",
            subtotal=bill5['subtotal'],
            discount=bill5['discount'],
            cover_charge=bill5['cover_charge'],
            vat_amount=bill5['vat_amount'],
            total=bill5['total'],
            created_by=cashier1.id,
            created_at=now_utc - timedelta(hours=2)
        )
        db.session.add(order5)
        db.session.flush()

        oi5_1 = OrderItem(
            restaurant_id=rest1.id,
            order_id=order5.id,
            dish_id=d_kacchi.id,
            dish_name_snapshot="Basmati Mutton Kacchi",
            unit_price_snapshot=Decimal("480.00"),
            quantity=1,
            kitchen_status="new",
            created_at=now_utc - timedelta(hours=2)
        )
        db.session.add(oi5_1)

        # Yesterday's Orders for Day-over-Day Comparison on Dashboard
        bill_yest = calculate_bill(subtotal=Decimal("1600.00"), discount_type="flat", discount_value=Decimal("0.00"), cover_charge=Decimal("0.00"), vat_rate=Decimal("5.00"), price_mode="exclusive")
        order_yest = Order(
            restaurant_id=rest1.id,
            order_no=6,
            type="dine_in",
            table_id=t_04.id,
            status="paid",
            payment_status="paid",
            subtotal=bill_yest['subtotal'],
            discount=bill_yest['discount'],
            cover_charge=bill_yest['cover_charge'],
            vat_amount=bill_yest['vat_amount'],
            total=bill_yest['total'],
            created_by=manager1.id,
            paid_at=yesterday_dt,
            created_at=yesterday_dt - timedelta(minutes=40)
        )
        db.session.add(order_yest)
        db.session.flush()

        oi_yest = OrderItem(
            restaurant_id=rest1.id,
            order_id=order_yest.id,
            dish_id=d_kacchi.id,
            dish_name_snapshot="Basmati Mutton Kacchi",
            unit_price_snapshot=Decimal("480.00"),
            quantity=3,
            kitchen_status="ready",
            created_at=yesterday_dt - timedelta(minutes=40)
        )
        pay_yest = Payment(
            restaurant_id=rest1.id,
            order_id=order_yest.id,
            method="card",
            amount=bill_yest['total'],
            reference="VISA-4092",
            status="completed",
            received_by=manager1.id,
            created_at=yesterday_dt
        )
        fe_yest = FinanceEntry(
            restaurant_id=rest1.id,
            type="sale",
            amount=bill_yest['total'],
            note=f"POS Dine In Order #{order_yest.order_no} (Card VISA-4092)",
            order_id=order_yest.id,
            created_by=manager1.id,
            entry_date=yesterday_dt
        )
        db.session.add_all([oi_yest, pay_yest, fe_yest])

        # ----------------------------------------------------------------------
        # Finance Entries (Daily Purchases & Operating Expenses)
        # ----------------------------------------------------------------------
        fe_pur1 = FinanceEntry(
            restaurant_id=rest1.id,
            type="purchase",
            amount=Decimal("3500.00"),
            note="15kg Fresh Mutton from Kaptan Bazar Meat Market",
            entry_date=now_utc - timedelta(hours=4),
            created_by=manager1.id
        )
        fe_pur2 = FinanceEntry(
            restaurant_id=rest1.id,
            type="purchase",
            amount=Decimal("1450.00"),
            note="50kg Chinigura Premium Rice from Badamtali Arot",
            entry_date=now_utc - timedelta(hours=3),
            created_by=manager1.id
        )
        fe_exp1 = FinanceEntry(
            restaurant_id=rest1.id,
            type="expense",
            amount=Decimal("1400.00"),
            note="12kg LP Gas Cylinder Refill",
            entry_date=now_utc - timedelta(hours=2),
            created_by=manager1.id
        )
        fe_exp2 = FinanceEntry(
            restaurant_id=rest1.id,
            type="expense",
            amount=Decimal("320.00"),
            note="Cleaning detergent, handwash and kitchen towels",
            entry_date=now_utc - timedelta(hours=1),
            created_by=manager1.id
        )
        db.session.add_all([fe_pur1, fe_pur2, fe_exp1, fe_exp2])

        # ----------------------------------------------------------------------
        # Audit Logs for Tenant 1
        # ----------------------------------------------------------------------
        audit1 = AuditLog(
            restaurant_id=rest1.id,
            user_id=owner1.id,
            action="RESTAURANT_INITIALIZED",
            record_type="Restaurant",
            record_id=rest1.id,
            details={"name": rest1.name, "bin": rest1.bin, "vat_rate": str(rest1.vat_rate)},
            created_at=now_utc - timedelta(days=2)
        )
        audit2 = AuditLog(
            restaurant_id=rest1.id,
            user_id=owner1.id,
            action="STAFF_CREATED",
            record_type="User",
            record_id=cashier1.id,
            details={"name": cashier1.name, "role": cashier1.role, "email": cashier1.email},
            created_at=now_utc - timedelta(days=1)
        )
        audit3 = AuditLog(
            restaurant_id=rest1.id,
            user_id=manager1.id,
            action="ORDER_CANCELLED",
            record_type="Order",
            record_id=order5.id,
            details={"order_no": 5, "reason": order5.cancel_reason},
            created_at=now_utc - timedelta(hours=2)
        )
        db.session.add_all([audit1, audit2, audit3])

        # ======================================================================
        # TENANT 2: Sultan's Feast (Dhanmondi) - Demonstrating Multi-Tenancy
        # ======================================================================
        print("Creating Tenant 2: Sultan's Feast (Dhanmondi) for Multi-Tenancy testing...")
        rest2 = Restaurant(
            name="Sultan's Feast (Dhanmondi)",
            phone="01799887766",
            address="Road 27 (Old), Dhanmondi, Dhaka",
            bin="987654321-0202",
            vat_rate=Decimal("7.50"),
            price_mode="inclusive",
            receipt_footer="Welcome to Sultans Feast! Visit again soon."
        )
        db.session.add(rest2)
        db.session.flush()

        owner2 = User(
            restaurant_id=rest2.id,
            name="Sultan Mahmud",
            email="owner@sultans.com",
            phone="01799887701",
            role="owner",
            is_active=True
        )
        owner2.set_password("owner123")

        cashier2 = User(
            restaurant_id=rest2.id,
            name="Imran Cashier",
            email="cashier@sultans.com",
            phone="01799887702",
            role="cashier",
            is_active=True
        )
        cashier2.set_password("cashier123")
        db.session.add_all([owner2, cashier2])
        db.session.flush()

        sp_sultan = Space(restaurant_id=rest2.id, name="Royal Dining")
        db.session.add(sp_sultan)
        db.session.flush()

        t_s1 = Table(restaurant_id=rest2.id, space_id=sp_sultan.id, name="S-01", capacity=4, cover_charge=Decimal("0.00"), status="open")
        t_s2 = Table(restaurant_id=rest2.id, space_id=sp_sultan.id, name="S-02", capacity=6, cover_charge=Decimal("0.00"), status="open")
        db.session.add_all([t_s1, t_s2])

        cat_sultan = Category(restaurant_id=rest2.id, name="Royal Specials", sort_order=1)
        db.session.add(cat_sultan)
        db.session.flush()

        d_s1 = Dish(restaurant_id=rest2.id, category_id=cat_sultan.id, name="Shahi Morog Polao", price=Decimal("380.00"), discount=Decimal("0.00"), veg_type="non_veg", prep_time_minutes=15, is_available=True)
        d_s2 = Dish(restaurant_id=rest2.id, category_id=cat_sultan.id, name="Mutton Reshmi Kebab (4 pcs)", price=Decimal("420.00"), discount=Decimal("0.00"), veg_type="non_veg", prep_time_minutes=20, is_available=True)
        db.session.add_all([d_s1, d_s2])

        # Sultan's Order #1: Demonstrates independent tenant order_no sequence
        bill_s1 = calculate_bill(subtotal=Decimal("380.00"), discount_type="flat", discount_value=Decimal("0.00"), cover_charge=Decimal("0.00"), vat_rate=Decimal("7.50"), price_mode="inclusive")
        order_s1 = Order(
            restaurant_id=rest2.id,
            order_no=1,
            type="quick",
            table_id=None,
            status="paid",
            payment_status="paid",
            subtotal=bill_s1['subtotal'],
            discount=bill_s1['discount'],
            cover_charge=bill_s1['cover_charge'],
            vat_amount=bill_s1['vat_amount'],
            total=bill_s1['total'],
            created_by=cashier2.id,
            paid_at=now_utc - timedelta(minutes=10),
            created_at=now_utc - timedelta(minutes=15)
        )
        db.session.add(order_s1)
        db.session.flush()

        oi_s1 = OrderItem(
            restaurant_id=rest2.id,
            order_id=order_s1.id,
            dish_id=d_s1.id,
            dish_name_snapshot="Shahi Morog Polao",
            unit_price_snapshot=Decimal("380.00"),
            quantity=1,
            kitchen_status="ready",
            created_at=now_utc - timedelta(minutes=15)
        )
        pay_s1 = Payment(
            restaurant_id=rest2.id,
            order_id=order_s1.id,
            method="cash",
            amount=bill_s1['total'],
            status="completed",
            received_by=cashier2.id,
            created_at=now_utc - timedelta(minutes=10)
        )
        fe_s1 = FinanceEntry(
            restaurant_id=rest2.id,
            type="sale",
            amount=bill_s1['total'],
            note=f"POS Quick Billing Order #{order_s1.order_no} (Cash)",
            order_id=order_s1.id,
            created_by=cashier2.id,
            entry_date=now_utc - timedelta(minutes=10)
        )
        db.session.add_all([oi_s1, pay_s1, fe_s1])

        # Commit all transactions
        db.session.commit()

        print("\n" + "="*60)
        print("  DEMO DATA SEEDED SUCCESSFULLY!")
        print("="*60)
        print("\n[Tenant 1: Kacchi Bhai (Banani)]")
        print("  • Owner:   owner@kacchi.com   / owner123   -> Full Admin, Settings & Staff")
        print("  • Manager: manager@kacchi.com / manager123 -> Operations, Menu, Finance & Audit")
        print("  • Cashier: cashier@kacchi.com / cashier123 -> Tablet POS Register & Payments")
        print("  • Kitchen: kitchen@kacchi.com / kitchen123 -> Real-time Kitchen Display (KDS)")
        print("\n[Tenant 2: Sultan's Feast (Dhanmondi)] (Multi-Tenancy Demo)")
        print("  • Owner:   owner@sultans.com  / owner123   -> Independent Menu, Orders & Cashbook")
        print("  • Cashier: cashier@sultans.com/ cashier123 -> Dedicated POS Register")
        print("\n[Live URLs to Explore]")
        print("  • Portal Login:      http://127.0.0.1:5000/auth/login")
        print("  • Register Portal:   http://127.0.0.1:5000/auth/register")
        print("  • Admin Dashboard:   http://127.0.0.1:5000/admin/")
        print("  • POS Terminal:      http://127.0.0.1:5000/pos/")
        print("  • Kitchen Display:   http://127.0.0.1:5000/kitchen/")
        print("  • Table Status:      http://127.0.0.1:5000/admin/tables/board")
        print("  • Finance Cashbook:  http://127.0.0.1:5000/admin/finance")
        print("  • Audit Log:         http://127.0.0.1:5000/admin/audit")
        print("="*60 + "\n")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Seed BanglaPOS demonstration data.")
    parser.add_argument(
        "--reset", "-r",
        action="store_true",
        help="Drop and recreate all database tables before seeding fresh demo data."
    )
    args = parser.parse_args()
    seed_database(reset=args.reset)
