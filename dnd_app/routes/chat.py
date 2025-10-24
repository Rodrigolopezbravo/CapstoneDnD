# dnd_app/chat.py
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
from flask_socketio import join_room, leave_room, emit, disconnect
from dnd_app import socketio
from dnd_app.oracle_db import get_connection_pool
import oracledb

chat_bp = Blueprint("chat_api", __name__, url_prefix="/api/chat")
pool = get_connection_pool()


def obtener_usuario(user_id):
    try:
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                out = cursor.var(oracledb.DB_TYPE_CURSOR)
                cursor.callproc("pkg_auth.obtener_usuario_por_id", [int(user_id), out])
                row = out.getvalue().fetchone()
                if row:
                    return {"id": row[0], "username": row[1], "email": row[2]}
    except Exception:
        current_app.logger.exception("Error obteniendo usuario")
    return None


@chat_bp.route("/partida/<int:id_partida>", methods=["GET"])
def traer_historial(id_partida):
    mensajes = []
    try:
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                out = cursor.var(oracledb.DB_TYPE_CURSOR)
                cursor.callproc("pkg_chat.traer_mensajes_partida", [id_partida, out])
                for row in out.getvalue():
                    mensajes.append({
                        "id_mensaje": row[0],
                        "id_partida": row[1],
                        "id_usuario": row[2],
                        "username": row[3],
                        "nombre_personaje": row[4],
                        "mensaje": row[5],
                        "fecha_envio": row[6].isoformat() if row[6] else None
                    })
        return jsonify(mensajes), 200
    except Exception as e:
        current_app.logger.exception("Error traer_historial")
        return jsonify({"error": str(e)}), 500


def get_current_user_id_or_none():
    try:
        verify_jwt_in_request(optional=True, locations=["cookies"])
        return get_jwt_identity()
    except Exception:
        return None


@socketio.on("connect")
def on_connect():
    user_id = get_current_user_id_or_none()
    if not user_id:
        emit("error", {"msg": "No autenticado (cookies JWT faltan o inválidas)."})
        return disconnect()
    request.sid_user_id = user_id
    emit("connected", {"msg": "connected", "user_id": user_id})


@socketio.on("join_partida")
def handle_join_partida(data):
    try:
        user_id = getattr(request, 'sid_user_id', get_current_user_id_or_none())
        if not user_id:
            emit("error", {"msg": "No autenticado. Reintente."})
            return disconnect()

        id_partida = int(data.get("id_partida")) if data.get("id_partida") else None
        id_personaje = int(data.get("id_personaje")) if data.get("id_personaje") else None

        if not id_partida or not id_personaje:
            emit("error", {"msg": "Faltan id_partida o id_personaje."})
            return

        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                id_usuario_personaje = cursor.callfunc(
                    "pkg_personaje.obtener_id_usuario_por_personaje",
                    oracledb.NUMBER,
                    [id_personaje]
                )

                if id_usuario_personaje is None:
                    emit("error", {"msg": "Personaje no existe."})
                    return

                if int(id_usuario_personaje) != int(user_id):
                    emit("error", {"msg": "No eres dueño del personaje."})
                    return

                p_id_partida_out = cursor.var(oracledb.NUMBER)
                cursor.callproc("pkg_partida.obtener_partida_por_personaje", [id_personaje, p_id_partida_out])
                partida_actual_personaje = p_id_partida_out.getvalue()

                if partida_actual_personaje is None or int(partida_actual_personaje) != int(id_partida):
                    emit("error", {"msg": "El personaje no está en esta partida."})
                    return

        room = f"partida_{id_partida}"
        join_room(room)

        usuario = obtener_usuario(user_id)
        username = usuario["username"] if usuario else f"user_{user_id}"

        emit("joined", {"ok": True, "room": room})
        emit("system", {"msg": f"{username} se unió a la partida."}, room=room, skip_sid=request.sid)

    except Exception as e:
        current_app.logger.exception("join_partida error")
        emit("error", {"msg": str(e)})


@socketio.on("leave_partida")
def handle_leave_partida(data):
    try:
        user_id = get_current_user_id_or_none()
        if not user_id:
            emit("error", {"msg": "No autenticado."})
            return

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
        user_id = getattr(request, 'sid_user_id', get_current_user_id_or_none())
        if not user_id:
            emit("error", {"msg": "No autenticado."})
            return

        id_partida = int(data.get("id_partida"))
        id_personaje = int(data.get("id_personaje")) if data.get("id_personaje") else None
        mensaje = data.get("mensaje", "").strip()

        if not mensaje:
            emit("error", {"msg": "Mensaje vacío."})
            return

        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                nombre_completo = cursor.callfunc(
                    "pkg_personaje.obtener_nombres_por_personaje",
                    oracledb.STRING,
                    [id_personaje]
                )

                cursor.callproc(
                    "pkg_chat.guardar_mensaje",
                    [id_partida, int(user_id), mensaje]
                )

                conn.commit()

        payload = {
            "id_partida": id_partida,
            "id_usuario": str(user_id),
            "username": nombre_completo,
            "mensaje": mensaje,
        }

        emit("new_message", payload, room=f"partida_{id_partida}")

    except oracledb.DatabaseError as db_e:
        current_app.logger.exception("DB error sending message")
        emit("error", {"msg": str(db_e)})
    except Exception as e:
        current_app.logger.exception("send_message error")
        emit("error", {"msg": str(e)})
