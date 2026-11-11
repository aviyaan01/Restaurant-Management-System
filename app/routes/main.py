from flask import Blueprint, render_template, jsonify
from sqlalchemy import text
from app.extensions import db

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def home():
    """Application home page displaying blueprint navigation and system status."""
    return render_template('home.html')

@main_bp.route('/health')
def health():
    """
    Health check endpoint:
    Verifies that the Flask app is responding and can query the PostgreSQL database.
    """
    try:
        # Execute basic query to verify DB connectivity
        db.session.execute(text('SELECT 1'))
        return jsonify({
            "status": "healthy",
            "database": "connected"
        }), 200
    except Exception as exc:
        return jsonify({
            "status": "unhealthy",
            "database": f"disconnected ({str(exc).strip()})"
        }), 503

