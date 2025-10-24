from flask import Blueprint, render_template, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
import oracledb
from dnd_app.oracle_db import get_connection_pool

partidas_bp = Blueprint("partidas", __name__)
pool = get_connection_pool()


@partidas_bp.route("/create", methods=["POST"])
@jwt_required()
def crear_partida():
    data = request.get_json()
    personaje_id = data.get("id_personaje")
    nombre = data.get("nombre_partida", "")

    if not personaje_id or not nombre:
        return jsonify({"error": "Faltan datos"}), 400

    try:
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                cursor.callproc("pkg_partida.crear_partida", [nombre, personaje_id])
            conn.commit()
        return jsonify({"message": "Partida creada correctamente"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@partidas_bp.route("/join", methods=["POST"])
@jwt_required()
def unirse_partida():
    data = request.get_json()
    codigo = data.get("codigo")
    personaje_id = data.get("id_personaje")

    try:
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                cursor.callproc("pkg_partida.unir_a_partida", [codigo, personaje_id])
            conn.commit()
        return jsonify({"message": "Personaje unido a la partida"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@partidas_bp.route("/ir/<int:id_personaje>", methods=["GET"])
@jwt_required()
def ir_a_partida(id_personaje):
    try:
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                out_id = cursor.var(oracledb.NUMBER)
                cursor.callproc("pkg_partida.obtener_partida_por_personaje", [id_personaje, out_id])

                partida = out_id.getvalue()
                if partida:
                    return jsonify({"status": "en_partida", "id_partida": int(partida)}), 200
                else:
                    return jsonify({"status": "sin_partida"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@partidas_bp.route("/partida/<int:id_partida>")
@jwt_required()
def ver_partida(id_partida):
    try:
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                out_cursor = cursor.var(oracledb.DB_TYPE_CURSOR)
                cursor.callproc("pkg_partida.traer_partida_por_id", [id_partida, out_cursor])

                row = out_cursor.getvalue().fetchone()
                if not row:
                    return "La partida no existe", 404

                partida = {
                    "id": row[0],
                    "nombre": row[1],
                    "estado": row[2],
                    "fecha_inicio": row[3],
                    "codigo": row[5]
                }

                id_usuario = get_jwt_identity()

                
                out_cursor_personaje = cursor.var(oracledb.DB_TYPE_CURSOR)
                cursor.callproc("pkg_partida.traer_jugadores_partida", [id_partida, out_cursor_personaje])

                id_personaje = None
                for jugador in out_cursor_personaje.getvalue():
                    
                    if int(jugador[0]) == int(id_usuario):
                        id_personaje = jugador[2]
                        break

        
        return render_template(
            "partida.html",
            partida=partida,
            id_personaje=int(id_personaje) if id_personaje else 0,
            id_usuario=int(id_usuario)
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@partidas_bp.route("/jugadores/<int:id_partida>")
@jwt_required()
def traer_jugadores(id_partida):
    try:
        jugadores = []
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                out_cursor = cursor.var(oracledb.DB_TYPE_CURSOR)
                cursor.callproc("pkg_partida.traer_jugadores_partida", [id_partida, out_cursor])

                for row in out_cursor.getvalue():
                    jugadores.append({
                        "id_usuario": row[0],
                        "usuario": row[1],
                        "id_personaje": row[2],
                        "personaje": row[3],
                        "clase": row[4]       
                    })

        return jsonify(jugadores), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
