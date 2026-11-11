from datetime import datetime, timezone, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, current_user, login_required
from app.extensions import db
from app.models.user import User
from app.forms.auth import LoginForm
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
