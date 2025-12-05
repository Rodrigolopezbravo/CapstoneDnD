from flask import Blueprint, request, jsonify, current_app, url_for, g
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
from flask_socketio import join_room, leave_room, emit, disconnect
from dnd_app import socketio 
from dnd_app.oracle_db import get_connection_pool
import oracledb
import os
<<<<<<< HEAD
import threading 

# --- CONFIGURACIÓN DE IA Y CREDENCIALES ---
=======
import re 
import json
>>>>>>> 9f554f145221fa60398f0190e0188e8564f02c63
import google.generativeai as genai

# Referencia global
APP_INSTANCE = None 

# Referencia global a la instancia de la aplicación (INICIALMENTE NONE)
# Se establecerá mediante setup_chat_module
APP_INSTANCE = None 

try:
    from dnd_app import walletcredentials 
    SECRETS_API_KEY = getattr(walletcredentials, 'GEMINI_API_KEY_LOCAL', None)
except ImportError:
<<<<<<< HEAD
    vertex_imports_ok = False
    
# Importamos el archivo de credenciales (Asumiendo dnd_app/walletcredentials.py)
try:
    from dnd_app import walletcredentials 
    SECRETS_API_KEY = getattr(walletcredentials, 'GEMINI_API_KEY_LOCAL', None)
except ImportError:
    SECRETS_API_KEY = None
    print("ADVERTENCIA: No se pudo importar walletcredentials. Usando variables de entorno.")

# Variables Globales
ID_USUARIO_GEMINI = 0 
NOMBRE_USUARIO_GEMINI = "DM Gema"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or SECRETS_API_KEY
=======
    SECRETS_API_KEY = None
    print("ADVERTENCIA: No se pudo importar walletcredentials.")

# Variables Globales
ID_USUARIO_GEMINI = 101 
NOMBRE_USUARIO_GEMINI = "DM Gema"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or SECRETS_API_KEY
ENTORNOS_PERMITIDOS = ["Bosque", "Pueblo", "Ciudad", "Ruina", "Mazmorra", "Camino"]
>>>>>>> 9f554f145221fa60398f0190e0188e8564f02c63

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
<<<<<<< HEAD
SYSTEM_PROMPT = f"""
Eres '{NOMBRE_USUARIO_GEMINI}', un Dungeon Master asistente para una partida de Dungeons and Dragons. 
Tu rol es ayudar al DM y a los jugadores. Responde preguntas sobre reglas, describe escenarios o interpreta a NPCs. 
El historial de chat incluye contexto. Responde siempre en español.
"""
# --------------------------
=======

SYSTEM_PROMPT = f"""
Eres '{NOMBRE_USUARIO_GEMINI}', un Dungeon Master asistente.
Tu rol es narrar la historia y describir escenarios.
REGLAS: Entornos válidos: {', '.join(ENTORNOS_PERMITIDOS)}.
Si narras un cambio de escena, usa código oculto: [[NUEVA_ESCENA|Nombre|Tipo]].
Responde en español.
"""
>>>>>>> 9f554f145221fa60398f0190e0188e8564f02c63

chat_bp = Blueprint("chat_api", __name__, url_prefix="/api/chat")
pool = get_connection_pool() 

<<<<<<< HEAD
# --- FUNCIÓN AUXILIAR PARA GUARDAR MENSAJE DE LA IA ---

def guardar_mensaje_ia_en_db(id_partida, mensaje_ia):
    """Guarda un mensaje en la base de datos asociado al ID de la IA (0)."""
    app = APP_INSTANCE or current_app
    try:
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                cursor.callproc(
                    "pkg_chat.guardar_mensaje",
                    [id_partida, ID_USUARIO_GEMINI, mensaje_ia]
                )
                conn.commit()
    except Exception as e:
        if app:
            app.logger.error(f"Error al guardar mensaje de IA en DB: {e}")
        else:
            print(f"Error al guardar mensaje de IA en DB (sin app context): {e}")

# --- SETUP DEL MÓDULO (PARA QUE __init__.py PUEDA LLAMARLA) ---
def setup_chat_module(app):
    """Inicializa la instancia global de la aplicación para el manejo de hilos."""
    global APP_INSTANCE
    APP_INSTANCE = app
    print("Chat Module: Flask app instance almacenada para manejo de hilos.")

# --- FUNCIONES AUXILIARES DE DB Y JWT ---
=======
# --- HELPERS GENERALES ---

def setup_chat_module(app):
    global APP_INSTANCE
    APP_INSTANCE = app
    print("Chat Module: Flask app instance almacenada.")
>>>>>>> 9f554f145221fa60398f0190e0188e8564f02c63

def obtener_usuario(user_id):
    app = APP_INSTANCE or current_app
    try:
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                out = cursor.var(oracledb.DB_TYPE_CURSOR)
                cursor.callproc("pkg_auth.obtener_usuario_por_id", [int(user_id), out])
                row = out.getvalue().fetchone()
<<<<<<< HEAD
                if row:
                    return {"id": row[0], "username": row[1], "email": row[2]}
    except Exception:
        if app:
            app.logger.exception("Error obteniendo usuario")
=======
                if row: return {"id": row[0], "username": row[1], "email": row[2]}
    except Exception: pass
>>>>>>> 9f554f145221fa60398f0190e0188e8564f02c63
    return None

def get_current_user_id_or_none():
    app = APP_INSTANCE or current_app
    try:
        verify_jwt_in_request(optional=True, locations=["cookies"])
        return get_jwt_identity()
<<<<<<< HEAD
    except Exception: # Puede fallar si no hay contexto (fuera de request/socket)
        return None
=======
    except Exception: return None
>>>>>>> 9f554f145221fa60398f0190e0188e8564f02c63

def guardar_mensaje_ia_en_db(id_partida, mensaje_ia):
    app = APP_INSTANCE or current_app
    try:
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                cursor.callproc("pkg_partida.guardar_mensaje_dm", [id_partida, mensaje_ia])
                conn.commit()
    except Exception as e:
        if app: app.logger.error(f"Error DB msg IA: {e}")

# --- HELPERS MONSTRUOS (SQL DIRECTO) ---

def obtener_contexto_combate(id_partida):
    if APP_INSTANCE is None: return ""
    info_texto = ""
    try:
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                out_cursor = cursor.var(oracledb.DB_TYPE_CURSOR)
                cursor.callproc("pkg_monstruos.info_partida_monstruos", [id_partida, out_cursor])
                
                jugadores_info = "Desconocido"
                lista_monstruos = []
                for row in out_cursor.getvalue():
                    if jugadores_info == "Desconocido":
                        jugadores_info = f"{row[0]} Jugadores (Niveles: {row[1]})"
                    lista_monstruos.append(f"{{ID: {row[2]}, Nombre: '{row[3]}', CR: {row[4]}}}")

                info_texto = (
                    f"DATOS DE PARTIDA:\n- Grupo: {jugadores_info}\n"
                    f"- Monstruos Disponibles: {', '.join(lista_monstruos)}\n"
                )
    except Exception as e:
        print(f"⚠️ Error info monstruos: {e}")
        return "Info: Grupo estándar."
    return info_texto

def insertar_monstruos_db(id_partida, lista_ids, lista_x, lista_y):
    if APP_INSTANCE is None: return
    try:
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT MAX(id_encuentro) FROM encuentro WHERE id_partida = :1", [id_partida])
                row = cursor.fetchone()
                if not row or row[0] is None: return
                id_encuentro = row[0]

                # SQL INSERCIÓN INTELIGENTE (SIN COLUMNA ESTADO PARA EVITAR ERROR)
                sql = """
                    INSERT INTO encuentro_monstruo (id_encuentro, id_monstruo, puntos_vida_actual, x, y)
                    SELECT :id_enc, m.id_monstruo, m.puntos_vida_maximo, :pos_x, :pos_y
                    FROM monstruo m
                    WHERE m.id_monstruo = :id_mon
                """
                
                datos = []
                for i in range(len(lista_ids)):
                    sx = max(0, min(14, lista_x[i]))
                    sy = max(0, min(14, lista_y[i]))
                    if sx == 7 and sy == 7: sx = 6 # Anti-colisión
                    
                    datos.append({
                        "id_enc": id_encuentro, "id_mon": lista_ids[i],
                        "pos_x": sx, "pos_y": sy
                    })
                
                cursor.executemany(sql, datos)
                conn.commit()
                print(f"✅ {len(lista_ids)} Monstruos insertados.")
    except Exception as e:
        print(f"❌ Error insertando monstruos: {e}")

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
                        "id_mensaje": row[0], "id_partida": row[1], "id_usuario": str(row[2]),
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
                sql = """
                    SELECT e.descripcion, e.fecha_evento 
                    FROM evento e JOIN encuentro en ON e.id_encuentro = en.id_encuentro
                    WHERE en.id_partida = :1 ORDER BY e.fecha_evento ASC
                """
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
<<<<<<< HEAD

    if not user_id:
        current_app.logger.warning("Socket.IO: Conexión rechazada (No autenticado).")
        emit("error", {"msg": "No autenticado. Por favor, inicia sesión."})
        return disconnect()

    g.user_id = user_id
    current_app.logger.info(f"Socket.IO: Cliente {user_id} conectado (SID: {request.sid})")
=======
    if not user_id: return disconnect()
    g.user_id = user_id
>>>>>>> 9f554f145221fa60398f0190e0188e8564f02c63
    emit("connected", {"msg": "connected", "user_id": user_id})

@socketio.on("join_partida")
def handle_join_partida(data):
    try:
        user_id = getattr(g, 'user_id', get_current_user_id_or_none())
        if not user_id: return disconnect()
        id_partida = int(data.get("id_partida"))
        room = f"partida_{id_partida}"
        join_room(room)
<<<<<<< HEAD

        if id_partida not in chat_histories:
            chat_histories[id_partida] = [{'role': 'user', 'parts': [SYSTEM_PROMPT]}]

=======
        if id_partida not in chat_histories: chat_histories[id_partida] = [{'role': 'user', 'parts': [SYSTEM_PROMPT]}]
>>>>>>> 9f554f145221fa60398f0190e0188e8564f02c63
        usuario = obtener_usuario(user_id)
        username = usuario["username"] if usuario else f"user_{user_id}"
        emit("system", {"msg": f"{username} entró."}, room=room, skip_sid=request.sid)
        emit("joined", {"ok": True, "room": room})
    except Exception as e: emit("error", {"msg": str(e)})

@socketio.on("leave_partida")
def handle_leave_partida(data):
    try:
        user_id = getattr(g, 'user_id', get_current_user_id_or_none())
        id_partida = int(data.get("id_partida"))
        leave_room(f"partida_{id_partida}")
        emit("left", {"ok": True})
    except Exception: pass

@socketio.on("send_message")
def handle_send_message(data):
    try:
        user_id = getattr(g, 'user_id', get_current_user_id_or_none()) 
        id_partida = int(data.get("id_partida"))
        id_personaje = int(data.get("id_personaje"))
        mensaje = data.get("mensaje", "").strip()
<<<<<<< HEAD

        if not mensaje:
            emit("error", {"msg": "Mensaje vacío."})
            return

        mensaje_limpio = mensaje.lower().strip()
        room = f"partida_{id_partida}"
        
        # 1. Comando @dm 
        if mensaje_limpio.startswith("@dm"):
            return handle_gemini_command(id_partida, user_id, mensaje, room)
        # 2. Comando @creartablero
        elif mensaje_limpio.startswith("@creartablero"):
            prompt = mensaje[len("@creartablero"):].strip()
            return handle_creartablero_command(id_partida, user_id, prompt, room)
        # 3. Comando @mapa
        elif mensaje_limpio.startswith("@mapa"):
            prompt = mensaje[len("@mapa"):].strip()
            return handle_mapa_command(id_partida, user_id, prompt, room)
        # 4. Comando @mostrar
        elif mensaje_limpio.startswith("@mostrar"):
            nombre_archivo = mensaje[len("@mostrar"):].strip()
            return handle_mostrar_command(id_partida, user_id, nombre_archivo, room)

        # --- Mensaje Normal ---
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                nombre_completo = cursor.callfunc("pkg_personaje.obtener_nombres_por_personaje", oracledb.STRING, [id_personaje])
                cursor.callproc("pkg_chat.guardar_mensaje", [id_partida, int(user_id), mensaje])
                conn.commit()
        payload = {"id_partida": id_partida, "id_usuario": str(user_id), "username": nombre_completo, "mensaje": mensaje}
        emit("new_message", payload, room=room)
        if id_partida in chat_histories:
            nombre_chat = nombre_completo if nombre_completo else f"User {user_id}"
            chat_histories[id_partida].append({'role': 'user', 'parts': [f"{nombre_chat}: {mensaje}"]})
=======
        if not mensaje: return
        room = f"partida_{id_partida}"
        
        if mensaje.lower().startswith("@iniciar"): return handle_iniciar_aventura_command(id_partida, user_id, room)
        if mensaje.lower().startswith("@evento"): return handle_gemini_command(id_partida, user_id, mensaje, room)
        if mensaje.lower().startswith("@nueva_escena"): return handle_nueva_escena_command(id_partida, user_id, mensaje[13:].strip(), room)

        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                nombre = cursor.callfunc("pkg_personaje.obtener_nombres_por_personaje", oracledb.STRING, [id_personaje])
                cursor.callproc("pkg_chat.guardar_mensaje", [id_partida, int(user_id), mensaje])
                conn.commit()
        
        emit("new_message", {"id_partida": id_partida, "id_usuario": str(user_id), "username": nombre, "mensaje": mensaje}, room=room)
        if id_partida in chat_histories: chat_histories[id_partida].append({'role': 'user', 'parts': [f"{nombre}: {mensaje}"]})
>>>>>>> 9f554f145221fa60398f0190e0188e8564f02c63

    except Exception: pass

# --- LOGICA IA ---

def handle_iniciar_aventura_command(id_partida, user_id, room):
    emit("nuevo_evento_ia", {"descripcion": "Iniciando aventura... ⏳"}, room=room)
    u = obtener_usuario(user_id)
    username = u["username"] if u else "Aventurero"
    socketio.start_background_task(run_inicio_aventura_ia, id_partida, room, username)
    return True

def run_inicio_aventura_ia(id_partida, room, username):
    if APP_INSTANCE is None or not gemini_model: return
    with APP_INSTANCE.app_context():
        try:
            lista = ", ".join(ENTORNOS_PERMITIDOS)
            prompt_setup = (
                f"Actúa como un Dungeon Master experto creando una nueva aventura. "
                f"1. Selecciona un entorno de: [{lista}]. "
                f"2. Crea un TÍTULO creativo y épico (NO uses el nombre '{username}' en el título). "
                f"RESPONDE SOLO: TITULO|ENTORNO"
            )
            resp_setup = gemini_model.generate_content(prompt_setup, safety_settings=dnd_safety_settings)
            texto_limpio = resp_setup.text.strip()
            
            if '|' in texto_limpio:
                partes = texto_limpio.split('|')
                nom = partes[0].strip()
                ent = partes[1].strip()
            else:
                nom = "El Comienzo del Viaje"
                ent = "Pueblo"

            if ent not in ENTORNOS_PERMITIDOS: ent = "Pueblo"

            with pool.acquire() as conn:
                with conn.cursor() as cursor:
                    cursor.callproc("pkg_partida.crear_encuentro", [id_partida, nom, ent])
                    conn.commit()

            prompt_narr = (
                f"System: La aventura comienza en '{nom}' ({ent}). "
                f"Narra una introducción inmersiva. El grupo acaba de llegar. "
                f"Si el lugar sugiere peligro, describe amenazas o monstruos acechando."
            )

            if id_partida not in chat_histories: chat_histories[id_partida] = [{'role': 'user', 'parts': [SYSTEM_PROMPT]}]
            chat_histories[id_partida].append({'role': 'user', 'parts': [prompt_narr]})
            run_gemini_request(id_partida, room)
        except Exception as e: APP_INSTANCE.logger.error(f"Error IA: {e}")

def handle_gemini_command(id_partida, user_id, mensaje, room):
<<<<<<< HEAD
    if not gemini_model: return emit("error", {"msg": "IA de Chat no configurada."})
    prompt = mensaje[len("@dm"):].strip()
    if id_partida in chat_histories: chat_histories[id_partida].append({'role': 'user', 'parts': [f"User {user_id}: {prompt}"]})
    emit("new_message", {"username": NOMBRE_USUARIO_GEMINI, "mensaje": "... 💭"}, room=room)
    thread = threading.Thread(target=run_gemini_request, args=(id_partida, room))
    thread.start()
=======
    prompt = mensaje[len("@evento"):].strip()
    if id_partida in chat_histories: chat_histories[id_partida].append({'role': 'user', 'parts': [f"User {user_id}: {prompt}"]})
    emit("nuevo_evento_ia", {"descripcion": "... 💭"}, room=room)
    socketio.start_background_task(run_gemini_request, id_partida, room)
>>>>>>> 9f554f145221fa60398f0190e0188e8564f02c63
    return True

def handle_nueva_escena_command(id_partida, user_id, params, room):
    partes = params.split('|')
    nom = partes[0].strip() if len(partes)>0 else "Escena"
    ent = partes[1].strip() if len(partes)>1 else "General"
    emit("nuevo_evento_ia", {"descripcion": f"Viajando a: {nom}..."}, room=room)
    try:
        with APP_INSTANCE.app_context():
            with pool.acquire() as conn:
                with conn.cursor() as cursor:
                    cursor.callproc("pkg_partida.crear_encuentro", [id_partida, nom, ent])
                    conn.commit()
    except Exception: pass

    prompt = f"System: El grupo llega a '{nom}' ({ent}). Narra. Si hay peligro, pon monstruos."
    if id_partida in chat_histories: chat_histories[id_partida].append({'role': 'user', 'parts': [prompt]})
    socketio.start_background_task(run_gemini_request, id_partida, room)
    return True

# --- FUNCIÓN QUE CONECTA CON PARTIDAS.PY (ESTO FALTABA) ---
def trigger_post_combat(id_partida, room):
    """
    Llamada por partidas.py cuando se detecta 'COMBATE_FINALIZADO'.
    Instruye a la IA a cerrar la escena y abrir una nueva.
    """
    if APP_INSTANCE is None or not gemini_model: return
    with APP_INSTANCE.app_context():
        try:
            instr = (
                "[SISTEMA]: ¡COMBATE FINALIZADO! Todos los enemigos han sido derrotados. "
                "1. Narra épicamente la victoria y cómo recuperan el aliento.\n"
                "2. Haz que el grupo avance inmediatamente hacia la siguiente zona.\n"
                "3. IMPORTANTE: Genera una NUEVA ESCENA usando: [[NUEVA_ESCENA|Nombre|Tipo]].\n"
                "4. Si la nueva escena es peligrosa, incluye JSON de monstruos."
            )
            
            if id_partida in chat_histories:
                chat_histories[id_partida].append({'role': 'user', 'parts': [instr]})
            
            # Reutilizamos la lógica principal para que procese el tag [[NUEVA_ESCENA]] si la IA lo genera
            run_gemini_request(id_partida, room)

        except Exception as e:
            APP_INSTANCE.logger.error(f"Error Post-Combate IA: {e}")

def run_gemini_request(id_partida, room):
<<<<<<< HEAD
    # *** ARREGLO FINAL: Usamos APP_INSTANCE para el contexto ***
    if APP_INSTANCE is None: 
        print("ERROR CRÍTICO: APP_INSTANCE no está definida en run_gemini_request.")
        return 
    
    with APP_INSTANCE.app_context():
        global gemini_model, chat_histories
        
        print(f"run_gemini_request: Iniciado para partida {id_partida}. Historial existe: {id_partida in chat_histories}")
        
        if id_partida not in chat_histories: 
            print(f"run_gemini_request: Saliendo, no hay historial para {id_partida}")
            return

        try:
            history = chat_histories[id_partida]
            print(f"run_gemini_request: Llamando a generate_content para partida {id_partida}...")
            
            response = gemini_model.generate_content(
                history,
                safety_settings=dnd_safety_settings
            )
            
            print(f"run_gemini_request: Respuesta recibida de la API.")
            
            try:
                gemini_response = response.text 
            except ValueError as ve:
                print(f"run_gemini_request: La respuesta fue bloqueada o vacía. Error: {ve}")
                gemini_response = f"[Respuesta bloqueada por filtros de seguridad o vacía]"
                if hasattr(response, 'prompt_feedback') and response.prompt_feedback.block_reason:
                     print(f"Motivo del bloqueo: {response.prompt_feedback.block_reason}")

            print(f"run_gemini_request: Contenido de la respuesta: '{gemini_response[:100]}...'") 
            
            chat_histories[id_partida].append({'role': 'model', 'parts': [gemini_response]})
            guardar_mensaje_ia_en_db(id_partida, gemini_response)
            
            print(f"run_gemini_request: Emitiendo respuesta final a la sala {room}...")
            socketio.emit("new_message", {"username": NOMBRE_USUARIO_GEMINI, "mensaje": gemini_response}, room=room)
            print(f"run_gemini_request: Respuesta emitida.")

        except Exception as e:
            print(f"run_gemini_request: ¡ERROR INESPERADO! {e}") 
            APP_INSTANCE.logger.error(f"Error en Gemini request: {e}", exc_info=True) 
            socketio.emit("new_message", {"username": NOMBRE_USUARIO_GEMINI, "mensaje": f"Error interno al procesar la solicitud: {e}"}, room=room)

def handle_creartablero_command(id_partida, user_id, descripcion, room):
    if not gemini_model: return emit("error", {"msg": "IA de Tablero no configurada."})
    if not descripcion: return emit("error", {"msg": "Debes especificar una descripción después de @creartablero"})
    emit("new_message", {"username": "Sistema", "mensaje": "Generando código del tablero... 💻"}, room=room)
    thread = threading.Thread(target=run_generar_codigo_tablero, args=(id_partida, descripcion, room))
    thread.start()
    return True

def run_generar_codigo_tablero(id_partida, descripcion, room):
    # *** ARREGLO FINAL: Usamos APP_INSTANCE para el contexto ***
    if APP_INSTANCE is None: 
        print("ERROR CRÍTICO: APP_INSTANCE no está definida en run_generar_codigo_tablero.")
        return 
        
    with APP_INSTANCE.app_context():
        try:
            client = genai.Client()
            modelo_compatible = client.models.get('gemini-pro')

            prompt_para_gemini = f"""Eres un asistente de D&D. Genera un fragmento de código HTML y CSS simple (usando <style> tags si es necesario) O SVG que represente visualmente esto de forma básica: '{descripcion}'. El código debe caber dentro de un div de 700px de ancho y 350px de alto. No incluyas <html> o <body>."""
            
            response = modelo_compatible.generate_content(prompt_para_gemini, safety_settings=dnd_safety_settings)
            codigo_generado = response.text.strip()
            
            # ... (limpieza de código) ...
            if codigo_generado.strip().startswith("```"): codigo_generado = '\n'.join(codigo_generado.split('\n')[1:-1]).strip()
            if codigo_generado.startswith("python"): codigo_generado = codigo_generado[6:].strip()
            if codigo_generado.startswith("html"): codigo_generado = codigo_generado[4:].strip()

            guardar_mensaje_ia_en_db(id_partida, f"Tablero creado: {descripcion}")
            socketio.emit('tablero_code', {'codigo': codigo_generado}, room=room)
        except Exception as e:
            APP_INSTANCE.logger.error(f"Error al generar código de tablero: {e}")
            socketio.emit("new_message", {"username": "Sistema", "mensaje": f"Error al crear código de tablero: {e}"}, room=room)

def handle_mapa_command(id_partida, user_id, prompt, room):
    if not vertex_imports_ok: return emit("error", {"msg": "La generación de imágenes con @mapa no está instalada/configurada."})
    if not prompt: return emit("error", {"msg": "Debes especificar una descripción para la imagen."})
    emit("new_message", {"username": "Sistema", "mensaje": "Generando imagen con Vertex AI... 🎨"}, room=room)
    # Pendiente implementar run_generar_mapa
    return True 

def handle_mostrar_command(id_partida, user_id, nombre_archivo, room):
    if not nombre_archivo: return emit("error", {"msg": "Debes especificar el nombre de un archivo."})
    if APP_INSTANCE is None: return emit("error", {"msg": "Error interno del servidor."})
    try:
        with APP_INSTANCE.app_context():
             with APP_INSTANCE.test_request_context('/'):
                url_imagen = url_for('static', filename=f'img/{nombre_archivo}', _external=False)
        
        emit("new_message", {"username": "Sistema", "mensaje": f"Mostrando imagen: {nombre_archivo}"}, room=room)
        socketio.emit('mapa_nuevo', {'url_imagen': url_imagen}, room=room)
        guardar_mensaje_ia_en_db(id_partida, f"Mostrando imagen estática: {nombre_archivo}")
        return True
        
    except Exception as e:
        APP_INSTANCE.logger.error(f"Error al generar URL estática: {e}")
        emit("error", {"msg": f"No se pudo encontrar la imagen estática '{nombre_archivo}'."})
        return False
=======
    if APP_INSTANCE is None or id_partida not in chat_histories: return
    with APP_INSTANCE.app_context():
        try:
            ctx = obtener_contexto_combate(id_partida)
            instr = (f"\n[SISTEMA]: Contexto:\n{ctx}\n"
                     "Si hay peligro, genera enemigos. AÑADE AL FINAL JSON con IDs y Coordenadas (0-14):\n"
                     "```json\n{\"monstruos\": [{\"id\": 12, \"x\": 5, \"y\": 6}]}```\n")
            
            hist = list(chat_histories[id_partida])
            hist.append({'role': 'user', 'parts': [instr]})

            resp = gemini_model.generate_content(hist, safety_settings=dnd_safety_settings)
            txt = resp.text
            
            # 1. Procesar JSON (Monstruos)
            ini = txt.find("```json")
            if ini != -1:
                fin = txt.find("```", ini+7)
                if fin != -1:
                    j_str = txt[ini+7:fin].strip()
                    try:
                        d = json.loads(j_str)
                        if "monstruos" in d:
                            ids, xs, ys = [], [], []
                            for m in d["monstruos"]:
                                xs_int = int(m["x"])
                                ys_int = int(m["y"])
                                if xs_int == 7 and ys_int == 7: xs_int = 6
                                ids.append(int(m["id"]))
                                xs.append(xs_int)
                                ys.append(ys_int)
                            insertar_monstruos_db(id_partida, ids, xs, ys)
                    except Exception: pass
                    txt = txt[:ini].strip() + "\n" + txt[fin+3:].strip()

            # 2. Procesar [[NUEVA_ESCENA]] (Generada por trigger_post_combat)
            patron = r"\[\[NUEVA_ESCENA\|(.*?)\|(.*?)\]\]"
            match = re.search(patron, txt)
            if match:
                n_escena = match.group(1).strip()
                t_entorno = match.group(2).strip()
                if t_entorno not in ENTORNOS_PERMITIDOS: t_entorno = "Ruina"
                try:
                    with pool.acquire() as conn:
                        with conn.cursor() as cursor:
                            cursor.callproc("pkg_partida.crear_encuentro", [id_partida, n_escena, t_entorno])
                            conn.commit()
                except: pass
                # Limpiamos el tag del texto visible
                txt = re.sub(patron, "", txt).strip()

            chat_histories[id_partida].append({'role': 'model', 'parts': [txt]})
            guardar_mensaje_ia_en_db(id_partida, txt)
            socketio.emit("nuevo_evento_ia", {"descripcion": txt}, room=room)

        except Exception as e: APP_INSTANCE.logger.error(f"Error IA: {e}")
>>>>>>> 9f554f145221fa60398f0190e0188e8564f02c63
