from flask import Flask, redirect, url_for, flash, session, render_template
from flask_login import current_user, logout_user
from config import get_config
from app.extensions import db, migrate, login_manager, csrf
from app.cli import register_commands

def create_app(config_class=None):
    """
    Application factory pattern: initializes extensions, sets configuration,
    and registers all blueprints.
    """
    app = Flask(__name__)

    # Load configuration
    if config_class is None:
        config_class = get_config()
    app.config.from_object(config_class)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    # Import models so SQLAlchemy and Flask-Migrate register tables
    from app import models

    # Register custom CLI commands
    register_commands(app)

    # LoginManager configuration
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'warning'

    @login_manager.user_loader
    def load_user(user_id):
        from app.models.user import User
        return db.session.get(User, int(user_id))

    @app.before_request
    def check_user_active_status():
        """
        Immediately log out any authenticated session whose account was deactivated
        by a restaurant owner or manager.
        """
        user_id = session.get('_user_id')
        if user_id:
            from app.models.user import User
            user = db.session.get(User, int(user_id))
            if user and not user.is_active:
                logout_user()
                session.clear()
                flash("Your account has been deactivated. Please contact your restaurant owner.", "danger")
                return redirect(url_for('auth.login'))

    @app.errorhandler(403)
    def forbidden_error(error):
        """Custom 403 Forbidden handler returning clean, role-aware error UI."""
        return render_template('errors/403.html', error=error), 403

    @app.errorhandler(404)
    def not_found_error(error):
        """Custom 404 handler for missing resources or cross-tenant guesses."""
        return render_template('errors/404.html', error=error), 404

    @app.errorhandler(500)
    def internal_server_error(error):
        """Custom 500 handler ensuring transactional rollback."""
        db.session.rollback()
        return render_template('errors/500.html', error=error), 500

    @app.after_request
    def set_security_headers(response):
        """Injects defense-in-depth HTTP security headers."""
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        if not app.debug:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        return response

    # ProxyFix middleware for production reverse proxy (Nginx -> Gunicorn)
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    # Register blueprints
    from app.routes.main import main_bp
    from app.routes.auth import auth_bp
    from app.routes.admin import admin_bp
    from app.routes.pos import pos_bp
    from app.routes.kitchen import kitchen_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(pos_bp, url_prefix='/pos')
    app.register_blueprint(kitchen_bp, url_prefix='/kitchen')

    return app
