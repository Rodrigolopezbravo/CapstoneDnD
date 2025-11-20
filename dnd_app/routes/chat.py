from flask import Blueprint, request, jsonify, current_app, url_for, g
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
from flask_socketio import join_room, leave_room, emit, disconnect
from dnd_app import socketio 
from dnd_app.oracle_db import get_connection_pool
import oracledb
import os
import threading 
import google.generativeai as genai
import base64
from io import BytesIO
import re

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
Eres '{NOMBRE_USUARIO_GEMINI}', un Dungeon Master asistente para una partida de D&D.
Tu rol es narrar la historia.
Si la historia cambia drásticamente de ubicación (ej. entran a una mazmorra, salen a un bosque), 
inicia tu respuesta con: [[NUEVA_ESCENA|Nombre del Lugar|Tipo de Entorno]].
Ejemplo: [[NUEVA_ESCENA|Bosque Sombrío|Bosque]] El aire se torna frío...
Si no hay cambio de zona, simplemente narra. Responde en español, y siempre habla en plural cuando te refieras a los jugadores.
"""

chat_bp = Blueprint("chat_api", __name__, url_prefix="/api/chat")
pool = get_connection_pool() 

# --- HELPERS ---
def guardar_mensaje_ia_en_db(id_partida, mensaje_ia):
    app = APP_INSTANCE or current_app
    try:
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                cursor.callproc("pkg_partida.guardar_mensaje_dm", [id_partida, mensaje_ia])
                conn.commit()
    except Exception as e:
        if app: app.logger.error(f"Error DB IA: {e}")

def setup_chat_module(app):
    global APP_INSTANCE
    APP_INSTANCE = app

def obtener_usuario(user_id):
    app = APP_INSTANCE or current_app
    try:
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                out = cursor.var(oracledb.DB_TYPE_CURSOR)
                cursor.callproc("pkg_auth.obtener_usuario_por_id", [int(user_id), out])
                row = out.getvalue().fetchone()
                if row: return {"id": row[0], "username": row[1], "email": row[2]}
    except Exception: pass
    return None

def get_current_user_id_or_none():
    try:
        verify_jwt_in_request(optional=True, locations=["cookies"])
        return get_jwt_identity()
    except Exception: return None

# --- RUTAS HTTP ---
@chat_bp.route("/partida/<int:id_partida>", methods=["GET"])
def traer_historial(id_partida):
    mensajes = []
    try:
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                out = cursor.var(oracledb.DB_TYPE_CURSOR)
                cursor.callproc("pkg_chat.traer_mensajes_partida", [id_partida, out])
                def read_data(value): return value.read() if hasattr(value, 'read') else value
                for row in out.getvalue():
                    mensajes.append({
                        "id_mensaje": row[0], "id_partida": row[1], "id_usuario": row[2],
                        "username": read_data(row[3]), "nombre_personaje": read_data(row[4]),
                        "mensaje": read_data(row[5]), "fecha_envio": row[6].isoformat() if row[6] else None
                    })
        return jsonify(mensajes), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@chat_bp.route("/eventos/<int:id_partida>", methods=["GET"])
def traer_historial_eventos(id_partida):
    eventos = []
    try:
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                sql = "SELECT e.descripcion, e.fecha_evento FROM evento e JOIN encuentro en ON e.id_encuentro = en.id_encuentro WHERE en.id_partida = :1 ORDER BY e.fecha_evento ASC"
                cursor.execute(sql, [id_partida])
                def read_data(value): return value.read() if hasattr(value, 'read') else value
                for row in cursor:
                    eventos.append({"descripcion": read_data(row[0]), "fecha": row[1].isoformat() if row[1] else None})
        return jsonify(eventos), 200
    except Exception: return jsonify([]), 200

# --- SOCKET IO ---
@socketio.on("connect")
def on_connect():
    user_id = get_current_user_id_or_none() 
    if not user_id: return disconnect()
    g.user_id = user_id
    emit("connected", {"msg": "connected", "user_id": user_id})

@socketio.on("join_partida")
def handle_join_partida(data):
    try:
        user_id = getattr(g, 'user_id', get_current_user_id_or_none())
        if not user_id: return disconnect()
        id_partida = int(data.get("id_partida"))
        id_personaje = int(data.get("id_personaje"))
        if not id_partida or not id_personaje: return
        
        room = f"partida_{id_partida}"
        join_room(room)
        
        # Solo inicializamos la memoria del historial, NO la narración automática
        if id_partida not in chat_histories:
             chat_histories[id_partida] = [{'role': 'user', 'parts': [SYSTEM_PROMPT]}]

        usuario = obtener_usuario(user_id)
        username = usuario["username"] if usuario else f"user_{user_id}"

        # 1. Mensaje de sistema (Chat)
        emit("system", {"msg": f"{username} se unió."}, room=room, skip_sid=request.sid)

        # 2. Saludo simple de DM Gema al jugador (Chat)
        # (Esto cumple con "solo salude a los jugadores que van entrando")
        saludo = f"¡Bienvenido a la mesa, {username}! Espera a que el grupo esté listo para comenzar."
        emit("new_message", {
            "id_partida": id_partida, 
            "id_usuario": str(ID_USUARIO_GEMINI), # ID 101
            "username": NOMBRE_USUARIO_GEMINI, 
            "mensaje": saludo
        }, room=room)
        
        emit("joined", {"ok": True, "room": room})
        
    except Exception as e:
        current_app.logger.exception("join error")
        emit("error", {"msg": str(e)})

@socketio.on("leave_partida")
def handle_leave_partida(data):
    # ... (Tu código leave) ...
    pass

@socketio.on("send_message")
def handle_send_message(data):
    try:
        user_id = getattr(g, 'user_id', get_current_user_id_or_none()) 
        if not user_id: return
        id_partida = int(data.get("id_partida"))
        id_personaje = int(data.get("id_personaje"))
        mensaje = data.get("mensaje", "").strip()
        if not mensaje: return

        room = f"partida_{id_partida}"
        msg_low = mensaje.lower()

        # *** NUEVO COMANDO: @iniciar ***
        if msg_low.startswith("@iniciar"):
            return handle_iniciar_aventura_command(id_partida, user_id, room)
        
        # Otros comandos
        elif msg_low.startswith("@evento"): return handle_gemini_command(id_partida, user_id, mensaje, room)
        elif msg_low.startswith("@nueva_escena"): return handle_nueva_escena_command(id_partida, user_id, mensaje[13:].strip(), room)
        elif msg_low.startswith("@creartablero"): return handle_creartablero_command(id_partida, user_id, mensaje[13:].strip(), room)
        elif msg_low.startswith("@mapa"): return handle_mapa_command(id_partida, user_id, mensaje[5:].strip(), room)
        elif msg_low.startswith("@mostrar"): return handle_mostrar_command(id_partida, user_id, mensaje[8:].strip(), room)

        # Mensaje Normal
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                nombre = cursor.callfunc("pkg_personaje.obtener_nombres_por_personaje", oracledb.STRING, [id_personaje])
                cursor.callproc("pkg_chat.guardar_mensaje", [id_partida, int(user_id), mensaje])
                conn.commit()
        
        emit("new_message", {"id_partida": id_partida, "id_usuario": str(user_id), "username": nombre, "mensaje": mensaje}, room=room)
        
        if id_partida in chat_histories:
            chat_histories[id_partida].append({'role': 'user', 'parts': [f"{nombre}: {mensaje}"]})
        
        # Respuesta automática de IA si no es comando (opcional, descomentar si quieres que responda siempre)
        # threading.Thread(target=run_gemini_request, args=(id_partida, room)).start()

    except Exception as e:
        current_app.logger.exception("send msg error")

# --- FUNCIONES IA ---

# *** NUEVA FUNCIÓN PARA COMANDO @iniciar ***
def handle_iniciar_aventura_command(id_partida, user_id, room):
    emit("new_message", {"username": "Sistema", "mensaje": "Iniciando la aventura... 🎲"}, room=room)
    emit("nuevo_evento_ia", {"descripcion": "El Dungeon Master está preparando el escenario... ⏳"}, room=room)
    
    # Lanza la lógica de inicio que antes estaba en el join
    # Usamos "el grupo" como nombre genérico o buscamos el nombre del usuario
    threading.Thread(target=run_inicio_aventura_ia, args=(id_partida, room, "el grupo")).start()
    return True

def run_inicio_aventura_ia(id_partida, room, username):
    if APP_INSTANCE is None: return
    with APP_INSTANCE.app_context():
        global gemini_model, chat_histories
        if not gemini_model: return
        try:
            prompt_setup = (
                f"Vas a iniciar una campaña de D&D. "
                "Genera un nombre creativo para el primer lugar/encuentro y una palabra para el entorno. "
                "Formato obligatorio: NOMBRE|ENTORNO"
            )
            resp_setup = gemini_model.generate_content(prompt_setup, safety_settings=dnd_safety_settings)
            datos = resp_setup.text.strip().split('|')
            nombre_enc = datos[0].strip() if len(datos) > 0 else "Inicio de Aventura"
            tipo_ent = datos[1].strip() if len(datos) > 1 else "Narración"
            
            try:
                with pool.acquire() as conn:
                    with conn.cursor() as cursor:
                        cursor.callproc("pkg_partida.crear_encuentro", [id_partida, nombre_enc, tipo_ent])
                        conn.commit()
            except Exception: pass

            prompt_narracion = (
                f"System: La aventura comienza en '{nombre_enc}' ({tipo_ent}). "
                "Describe la escena vívidamente, los olores, sonidos y la atmósfera. "
                "Termina preguntando qué hacen."
            )
            if id_partida not in chat_histories: chat_histories[id_partida] = [{'role': 'user', 'parts': [SYSTEM_PROMPT]}]
            
            chat_histories[id_partida].append({'role': 'user', 'parts': [prompt_narracion]})
            
            resp_narracion = gemini_model.generate_content(chat_histories[id_partida], safety_settings=dnd_safety_settings)
            texto = resp_narracion.text

            chat_histories[id_partida].append({'role': 'model', 'parts': [texto]})
            guardar_mensaje_ia_en_db(id_partida, texto)
            socketio.emit("nuevo_evento_ia", {"descripcion": texto}, room=room)

        except Exception as e:
            APP_INSTANCE.logger.error(f"Error inicio IA: {e}")
            socketio.emit("nuevo_evento_ia", {"descripcion": "Error al iniciar."}, room=room)

def handle_gemini_command(id_partida, user_id, mensaje, room):
    if not gemini_model: return
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
            try: txt = response.text 
            except: txt = "[Bloqueado]"
            
            # Detección Automática de Escena
            patron = r"\[\[NUEVA_ESCENA\|(.*?)\|(.*?)\]\]"
            match = re.search(patron, txt)
            if match:
                n_escena = match.group(1).strip()
                t_entorno = match.group(2).strip()
                try:
                    with pool.acquire() as conn:
                        with conn.cursor() as cursor:
                            cursor.callproc("pkg_partida.crear_encuentro", [id_partida, n_escena, t_entorno])
                            conn.commit()
                except: pass
                txt = re.sub(patron, "", txt).strip()

            chat_histories[id_partida].append({'role': 'model', 'parts': [txt]})
            guardar_mensaje_ia_en_db(id_partida, txt) 
            socketio.emit("nuevo_evento_ia", {"descripcion": txt}, room=room)
        except Exception as e:
            APP_INSTANCE.logger.error(f"Gemini error: {e}")

def handle_nueva_escena_command(id_partida, user_id, params, room):
    if not gemini_model: return emit("error", {"msg": "IA no configurada."})
    partes = params.split('|')
    nombre = partes[0].strip() if len(partes) > 0 else "Nueva Escena"
    entorno = partes[1].strip() if len(partes) > 1 else "General"
    emit("new_message", {"username": "Sistema", "mensaje": f"Viajando a: {nombre}..."}, room=room)
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
            run_gemini_request(id_partida, room) 

        except Exception as e:
            APP_INSTANCE.logger.error(f"Error cambio escena: {e}")

def handle_creartablero_command(id, u, d, r): return 
def run_generar_codigo_tablero(id, d, r): return 
def handle_mapa_command(id, u, p, r): return 
def handle_mostrar_command(id, u, n, r): return