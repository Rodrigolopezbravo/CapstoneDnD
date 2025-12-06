from flask import Blueprint, request, jsonify, current_app, url_for, g
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
from flask_socketio import join_room, leave_room, emit, disconnect
from dnd_app import socketio 
from dnd_app.oracle_db import get_connection_pool
import oracledb
import os
import re 
import json
import google.generativeai as genai

# Referencia global
APP_INSTANCE = None 

try:
    from dnd_app import walletcredentials 
    SECRETS_API_KEY = getattr(walletcredentials, 'GEMINI_API_KEY_LOCAL', None)
except ImportError:
    SECRETS_API_KEY = None
    print("ADVERTENCIA: No se pudo importar walletcredentials.")

ID_USUARIO_GEMINI = 101 
NOMBRE_USUARIO_GEMINI = "DM Gema"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or SECRETS_API_KEY
ENTORNOS_PERMITIDOS = ["Bosque", "Pueblo", "Ciudad", "Ruina", "Mazmorra", "Camino"]

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
Eres '{NOMBRE_USUARIO_GEMINI}', un Dungeon Master asistente.
Tu rol es narrar la historia y describir escenarios.
REGLAS: Entornos válidos: {', '.join(ENTORNOS_PERMITIDOS)}.
Si narras un cambio de escena, usa código oculto: [[NUEVA_ESCENA|Nombre|Tipo]].
IMPORTANTE: No generes una NUEVA_ESCENA si el grupo todavía está combatiendo.
Responde en español.
"""

chat_bp = Blueprint("chat_api", __name__, url_prefix="/api/chat")
pool = get_connection_pool() 

# --- HELPERS GENERALES ---

def setup_chat_module(app):
    global APP_INSTANCE
    APP_INSTANCE = app
    print("Chat Module: Flask app instance almacenada.")

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

def guardar_mensaje_ia_en_db(id_partida, mensaje_ia):
    app = APP_INSTANCE or current_app
    try:
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                cursor.callproc("pkg_partida.guardar_mensaje_dm", [id_partida, mensaje_ia])
                conn.commit()
    except Exception as e:
        if app: app.logger.error(f"Error DB msg IA: {e}")

# --- HELPERS MONSTRUOS ---

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
        print(f" Error info monstruos: {e}")
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
                    if sx == 7 and sy == 7: sx = 6 
                    
                    datos.append({
                        "id_enc": id_encuentro, "id_mon": lista_ids[i],
                        "pos_x": sx, "pos_y": sy
                    })
                
                cursor.executemany(sql, datos)
                conn.commit()
                print(f" {len(lista_ids)} Monstruos insertados.")
    except Exception as e:
        print(f" Error insertando monstruos: {e}")

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
                nombres_pj = {}
                cursor.execute("""
                    SELECT p.id_personaje, p.nombre 
                    FROM participacion pa
                    JOIN personaje p ON pa.id_personaje = p.id_personaje
                    WHERE pa.id_partida = :1
                """, [id_partida])
                for r in cursor:
                    nombres_pj[str(r[0])] = r[1]

                out_cursor = cursor.var(oracledb.DB_TYPE_CURSOR)
                cursor.callproc("pkg_partida.traer_eventos", [id_partida, out_cursor])
                
                def read_data(value): return value.read() if hasattr(value, 'read') else value
                
                for row in out_cursor.getvalue():
                    raw_desc = read_data(row[3])
                    fecha = row[4]
                    clean_desc = re.sub(
                        r"personaje ID (\d+)", 
                        lambda m: nombres_pj.get(m.group(1), m.group(0)), 
                        raw_desc
                    )
                    eventos.append({"descripcion": clean_desc, "fecha": fecha.isoformat() if fecha else None})
                    
        return jsonify(eventos), 200
    except Exception as e: 
        print(f"Error eventos: {e}")
        return jsonify([]), 200

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
        room = f"partida_{id_partida}"
        join_room(room)
        if id_partida not in chat_histories: 
            chat_histories[id_partida] = [{'role': 'user', 'parts': [SYSTEM_PROMPT]}]
        
        usuario = obtener_usuario(user_id)
        username = usuario["username"] if usuario else f"user_{user_id}"
        
        emit("system", {"msg": f"{username} entró."}, room=room, skip_sid=request.sid)
        emit("joined", {"ok": True, "room": room})
        
        # Avisar para recargar lista de jugadores
        emit("actualizar_jugadores", {"msg": "Nuevo jugador"}, room=room)

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

    except Exception: pass

# --- LOGICA IA ---

def handle_iniciar_aventura_command(id_partida, user_id, room):
    emit("nuevo_evento_ia", {"descripcion": "Iniciando aventura... "}, room=room)
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
                nom = partes[0].strip(); ent = partes[1].strip()
            else:
                nom = "El Comienzo del Viaje"; ent = "Pueblo"
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
    prompt = mensaje[len("@evento"):].strip()
    if id_partida in chat_histories: chat_histories[id_partida].append({'role': 'user', 'parts': [f"User {user_id}: {prompt}"]})
    emit("nuevo_evento_ia", {"descripcion": "... "}, room=room)
    socketio.start_background_task(run_gemini_request, id_partida, room)
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

def trigger_post_combat(id_partida, room):
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
            
            run_gemini_request(id_partida, room)

        except Exception as e:
            APP_INSTANCE.logger.error(f"Error Post-Combate IA: {e}")

def run_gemini_request(id_partida, room):
    if APP_INSTANCE is None or id_partida not in chat_histories: return
    with APP_INSTANCE.app_context():
        try:
            ctx = obtener_contexto_combate(id_partida)
            instr = (
                f"\n[SISTEMA]: Contexto:\n{ctx}\n"
                "Si hay peligro, genera enemigos. AÑADE AL FINAL JSON con IDs y Coordenadas (0-14):\n"
                "```json\n{\"monstruos\": [{\"id\": 12, \"x\": 5, \"y\": 6}]}```\n"
            )
            
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
                            
                            # Reiniciar Turnos y Parchar DM
                            try:
                                with pool.acquire() as conn:
                                    with conn.cursor() as cursor:
                                        cursor.callproc("pkg_turnos.iniciar_turnos", [id_partida])
                                        cursor.execute("""
                                            UPDATE turno_partida 
                                            SET acciones_totales = (SELECT COUNT(*) FROM participacion WHERE id_partida = :1 AND rol != 'dm'),
                                                acciones_restantes = (SELECT COUNT(*) FROM participacion WHERE id_partida = :1 AND rol != 'dm')
                                            WHERE id_partida = :1
                                        """, [id_partida])
                                        conn.commit()
                                print(" Turnos reiniciados tras aparición de monstruos.")
                            except Exception as e_turnos:
                                print(f" Alerta turno automático: {e_turnos}")

                    except Exception: pass
                    txt = txt[:ini].strip() + "\n" + txt[fin+3:].strip()

            # 2. Procesar [[NUEVA_ESCENA]] (Con Candado)
            patron = r"\[\[NUEVA_ESCENA\|(.*?)\|(.*?)\]\]"
            match = re.search(patron, txt)
            if match:
                combat_active = False
                try:
                    with pool.acquire() as conn:
                        with conn.cursor() as cursor:
                            cursor.execute("""
                                SELECT count(*) FROM encuentro_monstruo em 
                                JOIN encuentro e ON e.id_encuentro=em.id_encuentro
                                WHERE e.id_partida=:1 AND em.puntos_vida_actual > 0
                            """, [id_partida])
                            combat_active = cursor.fetchone()[0] > 0
                except: pass

                if not combat_active:
                    n_escena = match.group(1).strip()
                    t_entorno = match.group(2).strip()
                    if t_entorno not in ENTORNOS_PERMITIDOS: t_entorno = "Ruina"
                    try:
                        with pool.acquire() as conn:
                            with conn.cursor() as cursor:
                                cursor.callproc("pkg_partida.crear_encuentro", [id_partida, n_escena, t_entorno])
                                conn.commit()
                    except: pass
                else:
                    print(f"Bloqueado intento de IA de cambiar escena durante combate en partida {id_partida}")

                txt = re.sub(patron, "", txt).strip()

            chat_histories[id_partida].append({'role': 'model', 'parts': [txt]})
            guardar_mensaje_ia_en_db(id_partida, txt)
            socketio.emit("nuevo_evento_ia", {"descripcion": txt}, room=room)

        except Exception as e: APP_INSTANCE.logger.error(f"Error IA: {e}")