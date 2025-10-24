from flask import Flask, render_template, redirect, url_for, request
from flask_jwt_extended import JWTManager, verify_jwt_in_request, get_jwt_identity
from datetime import timedelta
from dnd_app.oracle_db import get_connection_pool
from flask_socketio import SocketIO
import oracledb
import os

jwt = JWTManager()
pool = get_connection_pool()
socketio = SocketIO(socketio = SocketIO(
    cors_allowed_origins=["http://127.0.0.1:5000"],
    cookie=True
))

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

    jwt.init_app(app)
    socketio.init_app(app)
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
    
    @app.route('/partida')
    def partida_page():
        return render_template('partida.html')

    @app.route('/register')
    def register_page():
        return render_template('register.html')
    
    @app.route('/partida/<int:id_partida>')
    def redirigir_partida(id_partida):
        return redirect(f"/api/partidas/partida/{id_partida}")


    @app.route('/')
    @app.route('/index')
    def index():
        return render_template('index.html')

    
    @app.route('/personajes')
    def personajes_page():
        return render_template('personaje.html')
    
    
    @app.route('/listar_personajes')
    def listar_personajes_page():
        return render_template('listar_personajes.html')
    

    @app.route('/personajes/detalle/<int:id_personaje>')
    def detalle_personaje_page(id_personaje):
        return render_template('detalle_personaje.html', id_personaje=id_personaje)
    
    @app.context_processor
    def inject_user():
        user = None
        try:
            # Verificar JWT desde cookies
            verify_jwt_in_request(optional=True, locations=["cookies"])
            user_id = get_jwt_identity()
            if user_id:
                with pool.acquire() as conn:
                    with conn.cursor() as cursor:
                        out_cursor = cursor.var(oracledb.DB_TYPE_CURSOR)
                        
                        cursor.callproc("pkg_auth.obtener_usuario_por_id", [int(user_id), out_cursor])
                        
                        row = out_cursor.getvalue().fetchone()
                        if row:
                            user = {
                                "id_usuario": row[0],
                                "username": row[1],
                                "email": row[2]
                            }
        except Exception:
            user = None

        return dict(current_user=user)

    return app