from flask import Flask, render_template, redirect, url_for, request
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager, verify_jwt_in_request, get_jwt_identity
from datetime import timedelta
from dnd_app.oracle_db import get_connection_pool
import os

db = SQLAlchemy()
jwt = JWTManager()
pool = get_connection_pool()

def create_app():
    app = Flask(__name__)

    # Configuración - cámbiala para producción
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URI", "sqlite:///dnd_app.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "modifica_esta_clave")
    
    # Configuración JWT
    app.config["JWT_TOKEN_LOCATION"] = ["cookies"]
    app.config["JWT_ACCESS_COOKIE_PATH"] = "/"
    app.config["JWT_COOKIE_SECURE"] = False  # En producción => True
    app.config["JWT_COOKIE_CSRF_PROTECT"] = False  # Desarrollo
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=24)

    db.init_app(app)
    jwt.init_app(app)

    # Importar y registrar blueprints
    from .routes.auth import auth_bp
    from .routes.personajes import personajes_bp
    from .routes.partidas import partidas_bp
    from .routes.encuentros import encuentros_bp
    from .routes.chat import chat_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(personajes_bp, url_prefix="/api/personajes")
    app.register_blueprint(partidas_bp, url_prefix="/api/partidas")
    app.register_blueprint(encuentros_bp, url_prefix="/api/encuentros")
    app.register_blueprint(chat_bp, url_prefix="/api/chat")

    # Páginas estáticas
    @app.route('/login')
    def login_page():
        return render_template('login.html')

    @app.route('/register')
    def register_page():
        return render_template('register.html')

    @app.route('/')
    @app.route('/index')
    def index():
        return render_template('index.html')

    # Context processor para inyectar usuario logeado en templates
    @app.context_processor
    def inject_user():
        user = None
        try:
            # Verificar JWT desde cookies
            verify_jwt_in_request(optional=True, locations=["cookies"])
            user_id = get_jwt_identity()
            if user_id:
                # Consultar usuario en Oracle
                with pool.acquire() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute("""
                            SELECT id_usuario, username, email
                            FROM Usuario
                            WHERE id_usuario = :1
                        """, (user_id,))
                        row = cursor.fetchone()
                        if row:
                            user = {
                                "id_usuario": row[0],
                                "username": row[1],
                                "email": row[2]
                            }
        except Exception:
            user = None
        return dict(current_user=user)

    # Crear tablas SQLite si no existen
    with app.app_context():
        from . import models
        db.create_all()

    return app
