import os
from datetime import timedelta
from dotenv import load_dotenv

# Load variables from .env into environment
load_dotenv()

class Config:
    """Base application configuration loaded from environment variables."""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'default-dev-secret-key-change-in-production')
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        'postgresql://postgres:postgres@localhost:5432/restaurant_pos_db'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # CSRF Protection via Flask-WTF
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None  # None keeps CSRF token valid for user session length

    # Secure, HttpOnly, SameSite Session Cookies & Inactivity Expiry
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', '0').lower() in ('1', 'true', 'yes')
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_DURATION = timedelta(days=7)
    REMEMBER_COOKIE_SAMESITE = 'Lax'

class DevelopmentConfig(Config):
    DEBUG = os.environ.get('FLASK_DEBUG', '1').lower() in ('1', 'true', 'yes')

class ProductionConfig(Config):
    DEBUG = False

config_by_name = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
}

def get_config():
    """Retrieve config class based on FLASK_ENV."""
    env = os.environ.get('FLASK_ENV', 'development').lower()
    return config_by_name.get(env, DevelopmentConfig)

