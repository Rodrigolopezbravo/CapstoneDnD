from flask import Flask, render_template, redirect, url_for, request
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from datetime import timedelta
import os

db = SQLAlchemy()
jwt = JWTManager()

def create_app():
    app = Flask(__name__)

    # Config - cámbiala para producción
    # Configuración de la base y JWT
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URI", "sqlite:///dnd_app.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "modifica_esta_clave")
    app.config["JWT_TOKEN_LOCATION"] = ["cookies"]
    app.config["JWT_ACCESS_COOKIE_PATH"] = "/"
    app.config["JWT_COOKIE_SECURE"] = False  # En producción => True
    app.config["JWT_COOKIE_CSRF_PROTECT"] = True
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=24)

    db.init_app(app)
    jwt.init_app(app)

    # importar rutas y registrarlas
    from .routes.auth import auth_bp
    from .routes.personajes import personajes_bp
    from .routes.partidas import partidas_bp
    from .routes.encuentros import encuentros_bp
    from .routes.chat import chat_bp

    # Context processor para inyectar usuario en plantillas
    from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
    from .models import Usuario

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(personajes_bp, url_prefix="/api/personajes")
    app.register_blueprint(partidas_bp, url_prefix="/api/partidas")
    app.register_blueprint(encuentros_bp, url_prefix="/api/encuentros")
    app.register_blueprint(chat_bp, url_prefix="/api/chat")

    @app.route('/login')
    def login_page():
        return render_template('login.html')

    @app.route('/register')
    def register_page():
        return render_template('register.html')
    
    # Ruta principal
    @app.route('/')
    def home():
        return render_template('index.html')
    
    @app.route('/index')
    def index():
        return render_template('index.html')
    
    @app.context_processor
    def inject_user():
        try:
            verify_jwt_in_request(optional=True)
            user_id = get_jwt_identity()
            user = Usuario.query.get(user_id) if user_id else None
        except:
            user = None
        return dict(current_user=user)

    # crear tablas si no existen
    with app.app_context():
        from . import models
        db.create_all()

    return app
