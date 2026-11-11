import click
from app.extensions import db
from app.models.restaurant import Restaurant
from app.models.user import User
from app.utils.audit import log_audit

def register_commands(app):
    """Register custom Flask CLI commands."""

    @app.cli.command('create-owner')
    def create_owner_command():
        """
        Creates a new restaurant tenant and prompts interactively for its first owner.
        Enforces Rule 6: No hardcoded or default passwords anywhere.
        """
        click.echo("\n" + "="*50)
        click.echo("  BanglaPOS: Register Restaurant & Initial Owner")
        click.echo("="*50 + "\n")

        # 1. Prompt restaurant information
        restaurant_name = click.prompt("Restaurant Name", type=str)
        restaurant_phone = click.prompt("Restaurant Phone (e.g., 01712345678)", type=str)
        restaurant_address = click.prompt("Restaurant Address (e.g., Dhanmondi 27, Dhaka)", type=str, default="")
        restaurant_bin = click.prompt("Business Identification Number / BIN (optional)", type=str, default="")

        # 2. Prompt owner information
        click.echo("\n--- Owner Details ---")
        owner_name = click.prompt("Owner Full Name", type=str)
        owner_email = click.prompt("Owner Email Address", type=str)
        owner_phone = click.prompt("Owner Mobile Number", type=str, default=restaurant_phone)

        # 3. Prompt password with verification and minimum length check
        while True:
            password = click.prompt("Owner Password (min 8 characters)", hide_input=True, confirmation_prompt=True)
            if len(password) >= 8:
                break
            click.echo("Error: Password must be at least 8 characters long. Please try again.")

        # 4. Create Restaurant
        restaurant = Restaurant(
            name=restaurant_name.strip(),
            phone=restaurant_phone.strip(),
            address=restaurant_address.strip(),
            bin=restaurant_bin.strip() or None,
            vat_rate=5.00,
            price_mode='exclusive',
            receipt_footer="ধন্যবাদ, আবার আসবেন! Powered by BanglaPOS"
        )
        db.session.add(restaurant)
        db.session.flush()  # Generates restaurant.id for foreign key

        # 5. Create Owner User
        owner = User(
            restaurant_id=restaurant.id,
            name=owner_name.strip(),
            email=owner_email.strip().lower(),
            phone=owner_phone.strip(),
            role='owner',
            is_active=True
        )
        owner.set_password(password)
        db.session.add(owner)
        db.session.commit()

        # 6. Audit log initial creation (Rule 5)
        log_audit(
            action='RESTAURANT_CREATED',
            record_type='Restaurant',
            record_id=restaurant.id,
            details={'name': restaurant.name, 'owner_email': owner.email},
            user_id=owner.id,
            restaurant_id=restaurant.id
        )

        click.echo("\n" + "-"*50)
        click.echo(f" SUCCESS: Restaurant '{restaurant.name}' (ID: {restaurant.id}) created.")
        click.echo(f" Owner account '{owner.email}' created with role 'owner'.")
        click.echo(" You can now run the app and sign in at: http://127.0.0.1:5000/auth/login")
        click.echo("-" * 50 + "\n")

    @app.cli.command('create-staff')
    @click.option('--restaurant-id', prompt='Restaurant ID', type=int, help='ID of restaurant tenant')
    @click.option('--role', prompt='Role (manager/cashier/kitchen)', type=click.Choice(['manager', 'cashier', 'kitchen']), help='Staff role')
    def create_staff_command(restaurant_id, role):
        """Helper command to create staff accounts (manager, cashier, kitchen) for a restaurant."""
        restaurant = db.session.get(Restaurant, restaurant_id)
        if not restaurant:
            click.echo(f"Error: Restaurant with ID {restaurant_id} not found.")
            return

        click.echo(f"\nAdding {role.upper()} for '{restaurant.name}'")
        name = click.prompt("Staff Full Name", type=str)
        email = click.prompt("Staff Email", type=str)
        phone = click.prompt("Staff Phone", type=str, default="")

        while True:
            password = click.prompt("Staff Password (min 8 characters)", hide_input=True, confirmation_prompt=True)
            if len(password) >= 8:
                break
            click.echo("Error: Password must be at least 8 characters long.")

        user = User(
            restaurant_id=restaurant.id,
            name=name.strip(),
            email=email.strip().lower(),
            phone=phone.strip(),
            role=role,
            is_active=True
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        log_audit(
            action='STAFF_CREATED',
            record_type='User',
            record_id=user.id,
            details={'name': user.name, 'role': user.role, 'email': user.email},
            user_id=user.id,
            restaurant_id=restaurant.id
        )

        click.echo(f"SUCCESS: Created {role} '{user.email}' for '{restaurant.name}'.\n")

