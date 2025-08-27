from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from datetime import timedelta
import os

db = SQLAlchemy()
jwt = JWTManager()

def create_app():
    app = Flask(__name__)

    # Config - cámbiala para producción
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URI", "sqlite:///dnd_app.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "cambia_esta_clave_en_produccion")
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=24)

    db.init_app(app)
    jwt.init_app(app)

    # importar rutas y registrarlas
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

    # crear tablas si no existen
    with app.app_context():
        from . import models
        db.create_all()

    return app
