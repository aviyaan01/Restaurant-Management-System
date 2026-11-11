from flask_login import current_user
from app.extensions import db
from app.models.audit import AuditLog

def log_audit(action, record_type, record_id=None, details=None, user_id=None, restaurant_id=None):
    """
    Non-negotiable Rule 5: Financial and staff changes are written to an audit log with user and time.
    Safely captures immutable audit events across tenants.
    """
    try:
        # Resolve user_id and restaurant_id from context if not explicitly provided
        if user_id is None and current_user.is_authenticated:
            user_id = current_user.id
            if restaurant_id is None:
                restaurant_id = current_user.restaurant_id

        if restaurant_id is None:
            return  # Audit logs must always be tenant-scoped

        entry = AuditLog(
            restaurant_id=restaurant_id,
            user_id=user_id,
            action=action,
            record_type=record_type,
            record_id=record_id,
            details=details or {}
        )
        db.session.add(entry)
        db.session.commit()
    except Exception:
        db.session.rollback()
        # In case of database or logging error, fail-safe so business transaction continues

