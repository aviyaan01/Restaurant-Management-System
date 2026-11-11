from functools import wraps
from flask import abort, flash, redirect, url_for, request
from flask_login import current_user

def role_required(*allowed_roles):
    """
    Non-negotiable Rule 2: Role checks happen on the server for every route, not just in the menu.
    Ensures the user is authenticated, active, and holds an authorized role.
    If unauthorized, returns HTTP 403 Forbidden on the server.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # 1. Authentication check
            if not current_user.is_authenticated:
                flash("Please log in to access this page.", "warning")
                return redirect(url_for('auth.login', next=request.url))

            # 2. Account active status check
            if not current_user.is_active:
                abort(403, description="Your account has been deactivated. Please contact your restaurant owner.")

            # 3. Role authorization check on the server
            if current_user.role not in allowed_roles:
                abort(403, description=f"Forbidden: '{current_user.role.title()}' role does not have permission to access this area.")

            return f(*args, **kwargs)
        return decorated_function
    return decorator
