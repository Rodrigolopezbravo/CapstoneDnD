from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
import oracledb
from dnd_app.oracle_db import get_connection_pool

personajes_bp = Blueprint("personajes", __name__)
pool = get_connection_pool()

@personajes_bp.route("/create", methods=["POST"])
@jwt_required()
def crear_personaje():
    user_id = get_jwt_identity()
    data = request.get_json()

    try:
        equipos_iniciales = ",".join(data.get("equipo", []))

        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                cursor.callproc(
                    "pkg_personaje.crear_personaje",
                    [
                        user_id,
                        data.get("nombre"),
                        int(data.get("clase")),
                        int(data.get("raza")),
                        equipos_iniciales,
                        int(data.get("fuerza")),
                        int(data.get("destreza")),
                        int(data.get("constitucion")),
                        int(data.get("inteligencia")),
                        int(data.get("sabiduria")),
                        int(data.get("carisma")),
                    ],
                )
            conn.commit()
    except Exception as e:
        print("Error al crear personaje:", e)
        return jsonify({"error": str(e)}), 500

    return jsonify({"message": "Personaje creado con éxito"}), 201


@personajes_bp.route("/my", methods=["GET"])
@jwt_required()
def my_personajes():
    user_id = get_jwt_identity()
    personajes = []

    try:
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                out_cursor = cursor.var(oracledb.DB_TYPE_CURSOR)
                
                
                cursor.callproc("pkg_personaje.traer_personajes_por_usuario", [user_id, out_cursor])
                
                result_cursor = out_cursor.getvalue()
                
               
                columnas = [col[0] for col in result_cursor.description]

                
                for row in result_cursor:
                    
                    personaje_dict = dict(zip(columnas, row))
                    personajes.append(personaje_dict)
                    
    except Exception as e:
        print(f"Error al listar personajes: {e}")
        return jsonify({"error": str(e)}), 500

    return jsonify(personajes), 200


@personajes_bp.route("/clases", methods=["GET"])
def obtener_clases():
    clases = []
    try:
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                out_cursor = cursor.var(oracledb.DB_TYPE_CURSOR)
                cursor.callproc("pkg_personaje.traer_todas_las_clases", [out_cursor])
                for row in out_cursor.getvalue():
                    clases.append({
                        "id": row[0],
                        "nombre": row[1]
                    })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify(clases), 200


@personajes_bp.route("/razas", methods=["GET"])
def obtener_razas():
    razas = []
    try:
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                out_cursor = cursor.var(oracledb.DB_TYPE_CURSOR)
                cursor.callproc("pkg_personaje.traer_todas_las_razas", [out_cursor])
                for row in out_cursor.getvalue():
                    razas.append({
                        "id": row[0],
                        "nombre": row[1]
                    })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify(razas), 200