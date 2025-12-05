from flask import Flask, render_template, redirect, url_for, request
from flask_jwt_extended import JWTManager, verify_jwt_in_request, get_jwt_identity
from datetime import timedelta
from dnd_app.oracle_db import get_connection_pool
from flask_socketio import SocketIO # Importa SocketIO
import oracledb
import os

jwt = JWTManager()
pool = get_connection_pool()

# *** CORRECCIÓN: Inicialización de SocketIO (solo una vez) ***
socketio = SocketIO(
    cors_allowed_origins=["http://127.0.0.1:5000", "http://localhost:5000"], # Añade localhost por si acaso
    cookie=True,
    # Puedes añadir manage_session=False si no usas sesiones de Flask
    # manage_session=False 
)

def create_app():
    app = Flask(__name__)

    # Configuración (simplificada)
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "modifica_esta_clave")
    app.config["JWT_TOKEN_LOCATION"] = ["cookies"]
    app.config["JWT_ACCESS_COOKIE_PATH"] = "/"
    app.config["JWT_COOKIE_SECURE"] = False # En producción => True
    app.config["JWT_COOKIE_CSRF_PROTECT"] = False # Desarrollo
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=24)
    # Eliminadas configuraciones de SQLAlchemy

    jwt.init_app(app)
    socketio.init_app(app)

    # Importar y registrar blueprints
    from .routes.auth import auth_bp
    from .routes.personajes import personajes_bp
    from .routes.partidas import partidas_bp
    from .routes.encuentros import encuentros_bp
    
    # *** CORRECCIÓN IMPORTANTE ***
    # Importamos el Blueprint Y la función setup
    from .routes.chat import chat_bp, setup_chat_module 

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(personajes_bp, url_prefix="/api/personajes")
    app.register_blueprint(partidas_bp, url_prefix="/api/partidas")
    app.register_blueprint(encuentros_bp, url_prefix="/api/encuentros")
    app.register_blueprint(chat_bp, url_prefix="/api/chat")

    # *** LLAMADA FINAL: Almacenar la instancia de la app ***
    # Esta línea asegura que APP_INSTANCE en chat.py se configure.
    setup_chat_module(app) 

    # --- Páginas estáticas ---
    @app.route('/login')
    def login_page(): return render_template('login.html')
    
    @app.route('/partida') # Esta ruta probablemente no la necesites si usas la de abajo
    def partida_page(): return render_template('partida.html') # Asumiendo que es una plantilla base
    
    @app.route('/register')
    def register_page(): return render_template('register.html')
    
    # Esta ruta redirige a la que maneja la lógica en partidas_bp
    @app.route('/partida/<int:id_partida>') 
    def redirigir_partida(id_partida): return redirect(f"/api/partidas/partida/{id_partida}")

    @app.route('/')
    @app.route('/index')
    def index(): return render_template('index.html')
    
    @app.route('/personajes')
    def personajes_page(): return render_template('personaje.html')
    
    @app.route('/listar_personajes')
    def listar_personajes_page(): return render_template('listar_personajes.html')
    
    @app.route('/personajes/detalle/<int:id_personaje>')
    def detalle_personaje_page(id_personaje): return render_template('detalle_personaje.html', id_personaje=id_personaje)
    
    @app.context_processor
    def inject_user():
        user = None
        try:
            verify_jwt_in_request(optional=True, locations=["cookies"])
            user_id = get_jwt_identity()
            if user_id:
                # Usar la función obtener_usuario del módulo de chat para evitar duplicar código
                # (Asegúrate de que la importación funcione)
                try:
                    from .routes.chat import obtener_usuario as obtener_usuario_chat
                    user = obtener_usuario_chat(user_id)
                except ImportError:
                     # Fallback si la importación no funciona (menos ideal)
                    with pool.acquire() as conn:
                        with conn.cursor() as cursor:
                            out_cursor = cursor.var(oracledb.DB_TYPE_CURSOR)
                            cursor.callproc("pkg_auth.obtener_usuario_por_id", [int(user_id), out_cursor])
                            row = out_cursor.getvalue().fetchone()
                            if row: user = {"id_usuario": row[0],"username": row[1],"email": row[2]}
        except Exception:
            user = None
        return dict(current_user=user)

    return app