from datetime import datetime, timezone, timedelta
from decimal import Decimal
from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, current_user, login_required
from app.extensions import db
from app.models.user import User
from app.models.restaurant import Restaurant
from app.models.table import Space, Table
from app.models.menu import Category
from app.forms.auth import LoginForm, RegisterForm
from app.utils.audit import log_audit

auth_bp = Blueprint('auth', __name__)

def redirect_for_role(role):
    """
    Directs authenticated user to their role-appropriate workspace.
    - Owner & Manager -> Admin Dashboard
    - Cashier -> POS Terminal
    - Kitchen -> Kitchen Display System (KDS)
    """
    if role in ('owner', 'manager'):
        return redirect(url_for('admin.dashboard'))
    elif role == 'cashier':
        return redirect(url_for('pos.terminal'))
    elif role == 'kitchen':
        return redirect(url_for('kitchen.display'))
    return redirect(url_for('main.home'))

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """
    Login endpoint supporting dual-identifier authentication (Email or Phone).
    Enforces server-side rate-limiting and temporary account lockout.
    """
    # If already logged in, redirect to role home
    if current_user.is_authenticated:
        return redirect_for_role(current_user.role)

    form = LoginForm()

    if form.validate_on_submit():
        ident = form.identifier.data.strip().lower()
        password = form.password.data

        # Lookup by email OR phone
        user = User.query.filter(
            (User.email == ident) | (User.phone == ident)
        ).first()

        now_utc = datetime.now(timezone.utc)

        if user:
            # 1. Check if user is currently locked out
            if user.locked_until:
                locked_until = user.locked_until
                if locked_until.tzinfo is None:
                    locked_until = locked_until.replace(tzinfo=timezone.utc)
                if locked_until > now_utc:
                    remaining_seconds = int((locked_until - now_utc).total_seconds())
                    remaining_minutes = max(1, (remaining_seconds + 59) // 60)
                    flash(
                        f"Account temporarily locked due to repeated failed attempts. Please retry in {remaining_minutes} minute(s).",
                        "danger"
                    )
                    return render_template('auth/login.html', form=form)

            # 2. Verify password with Werkzeug hashing
            if user.check_password(password):
                # 3. Check account active status
                if not user.is_active:
                    flash("Your account is deactivated. Please contact your restaurant owner.", "danger")
                    return render_template('auth/login.html', form=form)

                # Reset lockout counters on successful credentials
                user.failed_login_count = 0
                user.locked_until = None
                db.session.commit()

                # Establish session with HttpOnly/SameSite cookies
                login_user(user, remember=form.remember.data)
                session.permanent = True

                # Non-negotiable Rule 5: Audit log
                log_audit(
                    action='USER_LOGIN',
                    record_type='User',
                    record_id=user.id,
                    details={'email': user.email, 'role': user.role, 'method': 'password'},
                    user_id=user.id,
                    restaurant_id=user.restaurant_id
                )

                flash(f"Welcome back, {user.name} ({user.role.title()})!", "success")

                # Handle ?next= safe URL redirect
                next_page = request.args.get('next')
                if next_page and next_page.startswith('/') and not next_page.startswith('//'):
                    return redirect(next_page)

                return redirect_for_role(user.role)
            else:
                # Password incorrect: increment failure counter
                user.failed_login_count += 1
                max_attempts = 5

                if user.failed_login_count >= max_attempts:
                    user.locked_until = now_utc + timedelta(minutes=15)
                    db.session.commit()

                    log_audit(
                        action='ACCOUNT_LOCKED',
                        record_type='User',
                        record_id=user.id,
                        details={'failed_attempts': user.failed_login_count, 'lockout_minutes': 15},
                        user_id=user.id,
                        restaurant_id=user.restaurant_id
                    )

                    flash(
                        "Too many failed login attempts. Your account has been temporarily locked for 15 minutes.",
                        "danger"
                    )
                else:
                    db.session.commit()
                    attempts_left = max_attempts - user.failed_login_count
                    flash(
                        f"Invalid credentials. You have {attempts_left} attempt(s) remaining before temporary lockout.",
                        "danger"
                    )
        else:
            # Generic error to prevent identifier enumeration
            flash("Invalid email/phone or password.", "danger")

    return render_template('auth/login.html', form=form)

@auth_bp.route('/logout')
@login_required
def logout():
    """
    Safely terminates user session and clears session cookies.
    """
    user_id = current_user.id
    rest_id = current_user.restaurant_id
    email = current_user.email

    logout_user()
    session.clear()

    # Non-negotiable Rule 5: Audit log logout
    log_audit(
        action='USER_LOGOUT',
        record_type='User',
        record_id=user_id,
        details={'email': email},
        user_id=user_id,
        restaurant_id=rest_id
    )

    flash("You have been signed out safely.", "info")
    return redirect(url_for('auth.login'))

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """
    Self-service restaurant onboarding and owner account creation.
    Creates a new Restaurant tenant, primary Owner user, starter dining space & tables,
    starter category, and establishes the authenticated session.
    """
    if current_user.is_authenticated:
        return redirect_for_role(current_user.role)

    form = RegisterForm()
    if form.validate_on_submit():
        rest_name = form.restaurant_name.data.strip()
        rest_phone = form.restaurant_phone.data.strip()
        rest_address = (form.restaurant_address.data or '').strip() or 'Dhaka, Bangladesh'
        vat_rate = form.vat_rate.data if form.vat_rate.data is not None else Decimal('5.00')
        price_mode = form.price_mode.data or 'exclusive'

        owner_name = form.owner_name.data.strip()
        owner_email = form.owner_email.data.strip().lower()
        owner_phone = (form.owner_phone.data or '').strip() or rest_phone
        password = form.password.data

        # 1. Create Restaurant Tenant
        restaurant = Restaurant(
            name=rest_name,
            phone=rest_phone,
            address=rest_address,
            vat_rate=vat_rate,
            price_mode=price_mode,
            receipt_footer="ধন্যবাদ, আবার আসবেন! Powered by BanglaPOS"
        )
        db.session.add(restaurant)
        db.session.flush()

        # 2. Create Owner User
        owner = User(
            restaurant_id=restaurant.id,
            name=owner_name,
            email=owner_email,
            phone=owner_phone,
            role='owner',
            is_active=True
        )
        owner.set_password(password)
        db.session.add(owner)
        db.session.flush()

        # 3. Create starter space and tables for immediate POS readiness
        starter_space = Space(
            restaurant_id=restaurant.id,
            name="Main Dining Floor"
        )
        db.session.add(starter_space)
        db.session.flush()

        tables = [
            Table(
                restaurant_id=restaurant.id,
                space_id=starter_space.id,
                name="T-01",
                capacity=4,
                cover_charge=Decimal('0.00'),
                status='open'
            ),
            Table(
                restaurant_id=restaurant.id,
                space_id=starter_space.id,
                name="T-02",
                capacity=4,
                cover_charge=Decimal('0.00'),
                status='open'
            ),
            Table(
                restaurant_id=restaurant.id,
                space_id=starter_space.id,
                name="T-03",
                capacity=2,
                cover_charge=Decimal('0.00'),
                status='open'
            )
        ]
        starter_cat = Category(
            restaurant_id=restaurant.id,
            name="General Menu",
            sort_order=1
        )
        db.session.add_all(tables + [starter_cat])
        db.session.commit()

        # 4. Audit Log initial registration (Rule 5)
        log_audit(
            action='RESTAURANT_REGISTERED',
            record_type='Restaurant',
            record_id=restaurant.id,
            details={'name': restaurant.name, 'owner_email': owner.email},
            user_id=owner.id,
            restaurant_id=restaurant.id
        )

        # 5. Automatically log the new owner in
        login_user(owner)
        session.permanent = True

        flash(f"Congratulations! Restaurant '{restaurant.name}' has been created. Welcome to BanglaPOS!", "success")
        return redirect(url_for('admin.dashboard'))

    return render_template('auth/register.html', form=form)

