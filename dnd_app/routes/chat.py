from flask import Blueprint, request, jsonify, current_app, url_for, g
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
from flask_socketio import join_room, leave_room, emit, disconnect
from dnd_app import socketio 
from dnd_app.oracle_db import get_connection_pool
import oracledb
import os
import threading 

# --- CONFIGURACIÓN DE IA Y CREDENCIALES ---
import google.generativeai as genai
import base64
from io import BytesIO
import re # Necesario para detectar patrones de texto

# Referencia global a la instancia de la aplicación
APP_INSTANCE = None 

try:
    from google.genai import client as VertexClient
    from google.genai import types as VertexTypes
    vertex_imports_ok = True
except ImportError:
    vertex_imports_ok = False
    
try:
    from dnd_app import walletcredentials 
    SECRETS_API_KEY = getattr(walletcredentials, 'GEMINI_API_KEY_LOCAL', None)
except ImportError:
    SECRETS_API_KEY = None
    print("ADVERTENCIA: No se pudo importar walletcredentials. Usando variables de entorno.")

# Variables Globales
ID_USUARIO_GEMINI = 101 
NOMBRE_USUARIO_GEMINI = "DM Gema"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or SECRETS_API_KEY

gemini_model = None
chat_histories = {} 

if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        gemini_model = genai.GenerativeModel('gemini-2.5-flash') 
        print("Gemini (Chat) configurado exitosamente.")
    except Exception as e:
        print(f"Error al configurar Gemini (Chat): {e}")

dnd_safety_settings = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]
SYSTEM_PROMPT = f"""
Eres '{NOMBRE_USUARIO_GEMINI}', un Dungeon Master asistente para una partida de Dungeons and Dragons. 
Tu rol es ayudar al DM y a los jugadores. Responde preguntas sobre reglas, describe escenarios o interpreta a NPCs. 
El historial de chat (que NO verás) es solo para jugadores. Tus respuestas son eventos narrativos.
Responde siempre en español.
"""
# --------------------------

chat_bp = Blueprint("chat_api", __name__, url_prefix="/api/chat")
pool = get_connection_pool() 

# --- FUNCIÓN AUXILIAR PARA GUARDAR MENSAJE DE LA IA ---

def guardar_mensaje_ia_en_db(id_partida, mensaje_ia):
    """Guarda un mensaje en la base de datos usando el SP del DM."""
    app = APP_INSTANCE or current_app
    try:
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                cursor.callproc(
                    "pkg_partida.guardar_mensaje_dm",
                    [id_partida, mensaje_ia]
                )
                conn.commit()
    except Exception as e:
        if app:
            app.logger.error(f"Error al guardar mensaje de IA en DB: {e}")
        else:
            print(f"Error al guardar mensaje de IA en DB (sin app context): {e}")

# --- SETUP DEL MÓDULO ---
def setup_chat_module(app):
    """Inicializa la instancia global de la aplicación para el manejo de hilos."""
    global APP_INSTANCE
    APP_INSTANCE = app
    print("Chat Module: Flask app instance almacenada para manejo de hilos.")

# --- FUNCIONES AUXILIARES DE DB Y JWT ---

def obtener_usuario(user_id):
    app = APP_INSTANCE or current_app
    try:
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                out = cursor.var(oracledb.DB_TYPE_CURSOR)
                cursor.callproc("pkg_auth.obtener_usuario_por_id", [int(user_id), out])
                row = out.getvalue().fetchone()
                if row:
                    return {"id": row[0], "username": row[1], "email": row[2]}
    except Exception:
        if app:
            app.logger.exception("Error obteniendo usuario")
    return None

def get_current_user_id_or_none():
    app = APP_INSTANCE or current_app
    try:
        verify_jwt_in_request(optional=True, locations=["cookies"])
        return get_jwt_identity()
    except Exception: 
        return None

# --- RUTA HTTP (Historial Chat) ---

@chat_bp.route("/partida/<int:id_partida>", methods=["GET"])
def traer_historial(id_partida):
    mensajes = []
    try:
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                out = cursor.var(oracledb.DB_TYPE_CURSOR)
                cursor.callproc("pkg_chat.traer_mensajes_partida", [id_partida, out])
                
                def read_data(value):
                    if hasattr(value, 'read') and callable(value.read):
                        return value.read()
                    return value

                for row in out.getvalue():
                    mensajes.append({
                        "id_mensaje": row[0],
                        "id_partida": row[1],
                        "id_usuario": row[2],
                        "username": read_data(row[3]),
                        "nombre_personaje": read_data(row[4]),
                        "mensaje": read_data(row[5]),
                        "fecha_envio": row[6].isoformat() if row[6] else None
                    })
                
        return jsonify(mensajes), 200
    except Exception as e:
        current_app.logger.exception("Error traer_historial")
        return jsonify({"error": str(e)}), 500

# --- RUTA HTTP (Historial Eventos/IA) ---

@chat_bp.route("/eventos/<int:id_partida>", methods=["GET"])
def traer_historial_eventos(id_partida):
    eventos = []
    try:
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                sql = """
                    SELECT e.descripcion, e.fecha_evento 
                    FROM evento e
                    JOIN encuentro en ON e.id_encuentro = en.id_encuentro
                    WHERE en.id_partida = :1
                    ORDER BY e.fecha_evento ASC
                """
                cursor.execute(sql, [id_partida])
                
                def read_data(value):
                    return value.read() if hasattr(value, 'read') else value

                for row in cursor:
                    eventos.append({
                        "descripcion": read_data(row[0]),
                        "fecha": row[1].isoformat() if row[1] else None
                    })
        return jsonify(eventos), 200
    except Exception as e:
        return jsonify([]), 200

# --- MANEJO DE SOCKET.IO ---

@socketio.on("connect")
def on_connect():
    user_id = get_current_user_id_or_none() 
    if not user_id:
        current_app.logger.warning("Socket.IO: Conexión rechazada (No autenticado).")
        emit("error", {"msg": "No autenticado. Por favor, inicia sesión."})
        return disconnect()
    g.user_id = user_id
    current_app.logger.info(f"Socket.IO: Cliente {user_id} conectado (SID: {request.sid})")
    emit("connected", {"msg": "connected", "user_id": user_id})

@socketio.on("join_partida")
def handle_join_partida(data):
    try:
        user_id = getattr(g, 'user_id', get_current_user_id_or_none())
        if not user_id:
            emit("error", {"msg": "No autenticado. Reintente."})
            return disconnect()
        id_partida = int(data.get("id_partida")) if data.get("id_partida") else None
        id_personaje = int(data.get("id_personaje")) if data.get("id_personaje") else None
        if not id_partida or not id_personaje:
            emit("error", {"msg": "Faltan id_partida o id_personaje."})
            return
        room = f"partida_{id_partida}"
        join_room(room)
        
        narracion_inicio = False
        if id_partida not in chat_histories:
            chat_histories[id_partida] = [{'role': 'user', 'parts': [SYSTEM_PROMPT]}]
            narracion_inicio = True
        elif len(chat_histories.get(id_partida, [])) <= 1:
            narracion_inicio = True

        usuario = obtener_usuario(user_id)
        username = usuario["username"] if usuario else f"user_{user_id}"

        emit("system", {"msg": f"{username} se unió a la partida."}, room=room, skip_sid=request.sid)
        
        if narracion_inicio:
            # Crear encuentro inicial
            try:
                with pool.acquire() as conn:
                    with conn.cursor() as cursor:
                        cursor.callproc("pkg_partida.crear_encuentro", [id_partida, "Inicio de la Aventura", "Narración"])
                        conn.commit()
            except Exception: pass

            prompt_narracion = f"System: El juego comienza para {username}. Presenta la escena inicial."
            chat_histories[id_partida].append({'role': 'user', 'parts': [prompt_narracion]})
            emit("nuevo_evento_ia", {"descripcion": "... 💭"}, room=room)
            threading.Thread(target=run_gemini_request, args=(id_partida, room)).start()
        
        emit("joined", {"ok": True, "room": room})
        
    except Exception as e:
        current_app.logger.exception("join_partida error")
        emit("error", {"msg": str(e)})

@socketio.on("leave_partida")
def handle_leave_partida(data):
    try:
        user_id = getattr(g, 'user_id', get_current_user_id_or_none())
        if not user_id: return
        id_partida = int(data.get("id_partida"))
        room = f"partida_{id_partida}"
        leave_room(room)
        usuario = obtener_usuario(user_id)
        username = usuario["username"] if usuario else f"user_{user_id}"
        emit("left", {"ok": True})
        emit("system", {"msg": f"{username} salió de la partida."}, room=room)
    except Exception as e:
        current_app.logger.exception("leave_partida error")
        emit("error", {"msg": str(e)})

@socketio.on("send_message")
def handle_send_message(data):
    try:
        user_id = getattr(g, 'user_id', get_current_user_id_or_none()) 
        if not user_id:
            emit("error", {"msg": "No autenticado."})
            return

        id_partida = int(data.get("id_partida"))
        id_personaje = int(data.get("id_personaje")) if data.get("id_personaje") else None
        mensaje = data.get("mensaje", "").strip()
        if not mensaje:
            emit("error", {"msg": "Mensaje vacío."})
            return

        mensaje_limpio = mensaje.lower().strip()
        room = f"partida_{id_partida}"
        
        # --- COMANDOS ---
        
        # 1. @evento (Chat con IA)
        if mensaje_limpio.startswith("@evento"):
            return handle_gemini_command(id_partida, user_id, mensaje, room)
        
        # 2. @nueva_escena (¡RESTAURADO!)
        elif mensaje_limpio.startswith("@nueva_escena"):
            params = mensaje[len("@nueva_escena"):].strip()
            return handle_nueva_escena_command(id_partida, user_id, params, room)

        # 3. Otros comandos
        elif mensaje_limpio.startswith("@creartablero"):
            prompt = mensaje[len("@creartablero"):].strip()
            return handle_creartablero_command(id_partida, user_id, prompt, room)
        elif mensaje_limpio.startswith("@mapa"):
            prompt = mensaje[len("@mapa"):].strip()
            return handle_mapa_command(id_partida, user_id, prompt, room)
        elif mensaje_limpio.startswith("@mostrar"):
            nombre_archivo = mensaje[len("@mostrar"):].strip()
            return handle_mostrar_command(id_partida, user_id, nombre_archivo, room)

        # --- MENSAJE NORMAL ---
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                nombre_completo = cursor.callfunc("pkg_personaje.obtener_nombres_por_personaje", oracledb.STRING, [id_personaje])
                cursor.callproc("pkg_chat.guardar_mensaje", [id_partida, int(user_id), mensaje])
                conn.commit()
        
        payload = {"id_partida": id_partida, "id_usuario": str(user_id), "username": nombre_completo, "mensaje": mensaje}
        emit("new_message", payload, room=room)
        
        if id_partida in chat_histories:
            chat_histories[id_partida].append({'role': 'user', 'parts': [f"{nombre_completo}: {mensaje}"]})

    except Exception as e:
        current_app.logger.exception("send_message error")
        emit("error", {"msg": str(e)})


# --- FUNCIONES IA ---

def handle_gemini_command(id_partida, user_id, mensaje, room):
    if not gemini_model: return emit("error", {"msg": "IA de Chat no configurada."})
    prompt = mensaje[len("@evento"):].strip() 
    if id_partida in chat_histories: chat_histories[id_partida].append({'role': 'user', 'parts': [f"User {user_id}: {prompt}"]})
    
    emit("nuevo_evento_ia", {"descripcion": "... 💭"}, room=room) 
    threading.Thread(target=run_gemini_request, args=(id_partida, room)).start()
    return True

def run_gemini_request(id_partida, room):
    if APP_INSTANCE is None: return 
    with APP_INSTANCE.app_context():
        global gemini_model, chat_histories
        if id_partida not in chat_histories: return
        try:
            history = chat_histories[id_partida]
            response = gemini_model.generate_content(history, safety_settings=dnd_safety_settings)
            
            try:
                gemini_response = response.text 
            except ValueError:
                gemini_response = f"[Respuesta bloqueada]"

            chat_histories[id_partida].append({'role': 'model', 'parts': [gemini_response]})
            
            guardar_mensaje_ia_en_db(id_partida, gemini_response) 
            
            socketio.emit("nuevo_evento_ia", {"descripcion": gemini_response}, room=room)
        
        except Exception as e:
            APP_INSTANCE.logger.error(f"Error en Gemini request: {e}", exc_info=True) 
            socketio.emit("nuevo_evento_ia", {"descripcion": f"Error interno: {e}"}, room=room)

# --- FUNCIÓN NUEVA ESCENA (RESTAURADA) ---
def handle_nueva_escena_command(id_partida, user_id, params, room):
    if not gemini_model: return emit("error", {"msg": "IA no configurada."})
    
    partes = params.split('|')
    nombre = partes[0].strip() if len(partes) > 0 else "Nueva Escena"
    entorno = partes[1].strip() if len(partes) > 1 else "General"
    
    emit("new_message", {"username": "Sistema", "mensaje": f"Viajando a: {nombre} ({entorno})..."}, room=room)
    
    threading.Thread(target=run_cambio_escena, args=(id_partida, room, nombre, entorno)).start()
    return True

def run_cambio_escena(id_partida, room, nombre, entorno):
    if APP_INSTANCE is None: return
    with APP_INSTANCE.app_context():
        global gemini_model, chat_histories
        try:
            with pool.acquire() as conn:
                with conn.cursor() as cursor:
                    cursor.callproc("pkg_partida.crear_encuentro", [id_partida, nombre, entorno])
                    conn.commit()
            
            prompt = f"System: El grupo viaja a '{nombre}' ({entorno}). Describe la llegada."
            if id_partida not in chat_histories: chat_histories[id_partida] = []
            chat_histories[id_partida].append({'role': 'user', 'parts': [prompt]})
            
            response = gemini_model.generate_content(chat_histories[id_partida], safety_settings=dnd_safety_settings)
            texto = response.text
            
            chat_histories[id_partida].append({'role': 'model', 'parts': [texto]})
            guardar_mensaje_ia_en_db(id_partida, texto) 
            
            socketio.emit("nuevo_evento_ia", {"descripcion": texto}, room=room)
        except Exception as e:
            APP_INSTANCE.logger.error(f"Error cambio escena: {e}")
            socketio.emit("nuevo_evento_ia", {"descripcion": f"Error: {e}"}, room=room)

# --- OTRAS FUNCIONES ---

def handle_creartablero_command(id_partida, user_id, descripcion, room):
    if not gemini_model: return emit("error", {"msg": "IA no configurada."})
    if not descripcion: return emit("error", {"msg": "Falta descripción."})
    emit("new_message", {"username": "Sistema", "mensaje": "Generando código... 💻"}, room=room)
    threading.Thread(target=run_generar_codigo_tablero, args=(id_partida, descripcion, room)).start()
    return True

def run_generar_codigo_tablero(id_partida, descripcion, room):
    if APP_INSTANCE is None: return 
    with APP_INSTANCE.app_context():
        try:
            client = genai.Client()
            modelo_compatible = client.models.get('gemini-pro')
            prompt = f"Genera HTML/CSS simple para un tablero de D&D: '{descripcion}'. Solo div/style, sin html/body."
            response = modelo_compatible.generate_content(prompt, safety_settings=dnd_safety_settings)
            codigo = response.text.strip()
            
            if codigo.startswith("```"): codigo = '\n'.join(codigo.split('\n')[1:-1]).strip()
            if codigo.startswith("html"): codigo = codigo[4:].strip()
            
            guardar_mensaje_ia_en_db(id_partida, f"Tablero creado: {descripcion}")
            socketio.emit('tablero_code', {'codigo': codigo}, room=room)
        except Exception as e:
            APP_INSTANCE.logger.error(f"Error tablero: {e}")

def handle_mapa_command(id_partida, user_id, prompt, room):
    if not vertex_imports_ok: return emit("error", {"msg": "Vertex AI no configurado."})
    emit("new_message", {"username": "Sistema", "mensaje": "Generando imagen... 🎨"}, room=room)
    return True 

def handle_mostrar_command(id_partida, user_id, nombre_archivo, room):
    if not nombre_archivo: return emit("error", {"msg": "Falta nombre de archivo."})
    if APP_INSTANCE is None: return emit("error", {"msg": "Error interno."})
    try:
        with APP_INSTANCE.app_context():
             with APP_INSTANCE.test_request_context('/'):
                url_imagen = url_for('static', filename=f'img/{nombre_archivo}', _external=False)
        
        emit("new_message", {"username": "Sistema", "mensaje": f"Mostrando: {nombre_archivo}"}, room=room)
        socketio.emit('mapa_nuevo', {'url_imagen': url_imagen}, room=room)
        guardar_mensaje_ia_en_db(id_partida, f"Mostrando imagen: {nombre_archivo}")
        return True
    except Exception as e:
        APP_INSTANCE.logger.error(f"Error mostrar: {e}")
        return False