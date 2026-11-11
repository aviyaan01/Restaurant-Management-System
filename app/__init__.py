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
