from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
import oracledb
from dnd_app.oracle_db import get_connection_pool

tablero_bp = Blueprint("tablero", __name__)
pool = get_connection_pool()


@tablero_bp.route("/posicion/<int:id_partida>", methods=["GET"])
#@jwt_required()
def traer_posicion(id_partida):
    try:
        with pool.acquire() as conn:
            with conn.cursor() as cursor:

                out_cursor = cursor.var(oracledb.DB_TYPE_CURSOR)

                cursor.callproc(
                    "pkg_tablero.traer_posicion",
                    [id_partida, out_cursor]
                )

                row = out_cursor.getvalue().fetchone()

                if not row:
                    return jsonify({"x": 0, "y": 0}), 200

                return jsonify({"x": int(row[0]), "y": int(row[1])}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@tablero_bp.route("/mover", methods=["POST"])
#@jwt_required()
def mover_posicion():
    data = request.get_json()

    id_partida = data.get("id_partida")
    nueva_x = data.get("x")
    nueva_y = data.get("y")

    if id_partida is None or nueva_x is None or nueva_y is None:
        return jsonify({"error": "Faltan parámetros"}), 400

    try:
        with pool.acquire() as conn:
            with conn.cursor() as cursor:

                cursor.callproc(
                    "pkg_tablero.mover_posicion",
                    [id_partida, nueva_x, nueva_y]
                )
                conn.commit()

        return jsonify({
            "ok": True,
            "x": nueva_x,
            "y": nueva_y
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
