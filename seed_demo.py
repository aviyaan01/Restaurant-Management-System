import os
import sys
from decimal import Decimal

# Ensure project root in path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app import create_app
from app.extensions import db
from app.models.restaurant import Restaurant
from app.models.user import User
from app.models.menu import Category, Dish
from app.models.table import Space, Table

app = create_app()

def seed():
    with app.app_context():
        db.create_all()

        existing = Restaurant.query.first()
        if existing:
            print(f"Database already contains restaurant '{existing.name}' (ID: {existing.id}).")
            return

        print("Seeding demo restaurant, staff, spaces, tables, and menu...")

        # 1. Restaurant
        rest = Restaurant(
            name="Kacchi Bhai (Banani)",
            phone="01711223344",
            address="Road 11, Block D, Banani, Dhaka-1213",
            bin="123456789-0101",
            vat_rate=Decimal("5.00"),
            price_mode="exclusive",
            receipt_footer="ধন্যবাদ, আবার আসবেন! Powered by BanglaPOS"
        )
        db.session.add(rest)
        db.session.flush()

        # 2. Staff Accounts for all 4 roles
        owner = User(
            restaurant_id=rest.id,
            name="Karim Owner",
            email="owner@kacchi.com",
            phone="01711223301",
            role="owner",
            is_active=True
        )
        owner.set_password("owner123")

        manager = User(
            restaurant_id=rest.id,
            name="Rahim Manager",
            email="manager@kacchi.com",
            phone="01711223302",
            role="manager",
            is_active=True
        )
        manager.set_password("manager123")

        cashier = User(
            restaurant_id=rest.id,
            name="Habib Cashier",
            email="cashier@kacchi.com",
            phone="01711223303",
            role="cashier",
            is_active=True
        )
        cashier.set_password("cashier123")

        kitchen = User(
            restaurant_id=rest.id,
            name="Chef Rafiq",
            email="kitchen@kacchi.com",
            phone="01711223304",
            role="kitchen",
            is_active=True
        )
        kitchen.set_password("kitchen123")

        db.session.add_all([owner, manager, cashier, kitchen])
        db.session.flush()

        # 3. Spaces & Tables
        sp1 = Space(restaurant_id=rest.id, name="Ground Floor")
        sp2 = Space(restaurant_id=rest.id, name="AC Dining Hall")
        db.session.add_all([sp1, sp2])
        db.session.flush()

        tables = [
            Table(restaurant_id=rest.id, space_id=sp1.id, name="T-01", capacity=4, cover_charge=Decimal("0.00"), status="open"),
            Table(restaurant_id=rest.id, space_id=sp1.id, name="T-02", capacity=4, cover_charge=Decimal("0.00"), status="open"),
            Table(restaurant_id=rest.id, space_id=sp1.id, name="T-03", capacity=2, cover_charge=Decimal("0.00"), status="open"),
            Table(restaurant_id=rest.id, space_id=sp1.id, name="T-04", capacity=6, cover_charge=Decimal("0.00"), status="open"),
            Table(restaurant_id=rest.id, space_id=sp2.id, name="AC-1", capacity=4, cover_charge=Decimal("50.00"), status="open"),
            Table(restaurant_id=rest.id, space_id=sp2.id, name="AC-2", capacity=4, cover_charge=Decimal("50.00"), status="open"),
        ]
        db.session.add_all(tables)

        # 4. Categories & Dishes
        c1 = Category(restaurant_id=rest.id, name="Biryani and Mains", sort_order=1)
        c2 = Category(restaurant_id=rest.id, name="Sides and Desserts", sort_order=2)
        c3 = Category(restaurant_id=rest.id, name="Beverages", sort_order=3)
        db.session.add_all([c1, c2, c3])
        db.session.flush()

        dishes = [
            Dish(restaurant_id=rest.id, category_id=c1.id, name="Basmati Mutton Kacchi", price=Decimal("480.00"), discount=Decimal("0.00"), veg_type="non_veg", prep_time_minutes=15, is_available=True),
            Dish(restaurant_id=rest.id, category_id=c1.id, name="Chicken Roast Polao", price=Decimal("350.00"), discount=Decimal("0.00"), veg_type="non_veg", prep_time_minutes=12, is_available=True),
            Dish(restaurant_id=rest.id, category_id=c1.id, name="Beef Tehari (Old Dhaka)", price=Decimal("320.00"), discount=Decimal("20.00"), veg_type="non_veg", prep_time_minutes=10, is_available=True),
            Dish(restaurant_id=rest.id, category_id=c2.id, name="Special Borhani (250ml)", price=Decimal("80.00"), discount=Decimal("10.00"), veg_type="veg", prep_time_minutes=2, is_available=True),
            Dish(restaurant_id=rest.id, category_id=c2.id, name="Shahi Jafrani Firni", price=Decimal("120.00"), discount=Decimal("0.00"), veg_type="veg", prep_time_minutes=5, is_available=True),
            Dish(restaurant_id=rest.id, category_id=c3.id, name="Fresh Lime Soda", price=Decimal("60.00"), discount=Decimal("0.00"), veg_type="veg", prep_time_minutes=3, is_available=True),
            Dish(restaurant_id=rest.id, category_id=c3.id, name="Mineral Water 500ml", price=Decimal("25.00"), discount=Decimal("0.00"), veg_type="veg", prep_time_minutes=1, is_available=True),
        ]
        db.session.add_all(dishes)

        db.session.commit()
        print("Demo data seeded successfully into database!")
        print("\nLogin Credentials:")
        print("  Owner:   owner@kacchi.com   / owner123")
        print("  Manager: manager@kacchi.com / manager123")
        print("  Cashier: cashier@kacchi.com / cashier123")
        print("  Kitchen: kitchen@kacchi.com / kitchen123")

if __name__ == '__main__':
    seed()

