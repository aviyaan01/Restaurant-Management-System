import csv
import io
import json
from datetime import datetime, date, time, timezone
from app.extensions import db
from app.models.audit import AuditLog

def get_audit_logs(
    restaurant_id: int,
    user_id: int = None,
    action: str = None,
    record_type: str = None,
    start_date: date = None,
    end_date: date = None,
    page: int = 1,
    per_page: int = 25
):
    """
    Returns paginated audit log records for a restaurant tenant.
    Non-negotiable Rule 1: Always filtered by restaurant_id.
    Non-negotiable Rule 5: Immutable compliance logs.
    """
    query = AuditLog.query.filter_by(restaurant_id=restaurant_id)

    if user_id:
        try:
            uid = int(user_id)
            if uid > 0:
                query = query.filter(AuditLog.user_id == uid)
        except (ValueError, TypeError):
            pass

    if action and action.strip():
        query = query.filter(AuditLog.action == action.strip())

    if record_type and record_type.strip():
        query = query.filter(AuditLog.record_type == record_type.strip())

    if start_date:
        start_dt = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
        query = query.filter(AuditLog.created_at >= start_dt)

    if end_date:
        end_dt = datetime.combine(end_date, time.max, tzinfo=timezone.utc)
        query = query.filter(AuditLog.created_at <= end_dt)

    pagination = query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )

    return pagination

def export_audit_logs_csv(
    restaurant_id: int,
    user_id: int = None,
    action: str = None,
    record_type: str = None,
    start_date: date = None,
    end_date: date = None
) -> str:
    """
    Generates a CSV string of tenant audit logs for compliance audits and off-server archiving.
    """
    query = AuditLog.query.filter_by(restaurant_id=restaurant_id)

    if user_id:
        try:
            uid = int(user_id)
            if uid > 0:
                query = query.filter(AuditLog.user_id == uid)
        except (ValueError, TypeError):
            pass

    if action and action.strip():
        query = query.filter(AuditLog.action == action.strip())

    if record_type and record_type.strip():
        query = query.filter(AuditLog.record_type == record_type.strip())

    if start_date:
        start_dt = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
        query = query.filter(AuditLog.created_at >= start_dt)

    if end_date:
        end_dt = datetime.combine(end_date, time.max, tzinfo=timezone.utc)
        query = query.filter(AuditLog.created_at <= end_dt)

    logs = query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)

    # Header Row
    writer.writerow([
        "Log ID",
        "Timestamp (UTC)",
        "Staff Name",
        "Staff Email",
        "Staff Role",
        "Action",
        "Record Type",
        "Record ID",
        "Details JSON"
    ])

    for log in logs:
        user_name = log.user.name if log.user else "System"
        user_email = log.user.email if log.user else ""
        user_role = log.user.role if log.user else "system"
        ts = log.created_at.strftime('%Y-%m-%d %H:%M:%S') if log.created_at else ""
        details_str = json.dumps(log.details or {}, ensure_ascii=False)

        writer.writerow([
            log.id,
            ts,
            user_name,
            user_email,
            user_role,
            log.action,
            log.record_type,
            log.record_id or "",
            details_str
        ])

    return output.getvalue()

