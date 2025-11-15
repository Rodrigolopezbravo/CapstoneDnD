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

@personajes_bp.route("/<int:id_personaje>", methods=["GET"])
@jwt_required()
def get_detalle_personaje(id_personaje):
    user_id = get_jwt_identity()

    try:
        with pool.acquire() as conn:
            with conn.cursor() as cursor:

                detalle_cursor = cursor.var(oracledb.DB_TYPE_CURSOR)
                cursor.callproc(
                    "pkg_personaje.traer_detalle_personaje",
                    [user_id, id_personaje, detalle_cursor]
                )

                result_cursor = detalle_cursor.getvalue()
                columnas_det = [col[0] for col in result_cursor.description]

                first_row = result_cursor.fetchone()
                if not first_row:
                    return jsonify({"error": "Personaje no encontrado o no te pertenece"}), 404

                personaje_detalle = dict(zip(columnas_det, first_row))

                for campo in ("NOMBRE_EQUIPO", "CANTIDAD"):
                    personaje_detalle.pop(campo, None)

                equipo_cursor = cursor.var(oracledb.DB_TYPE_CURSOR)
                cursor.callproc(
                    "pkg_inventario.traer_equipo_equipado",
                    [id_personaje, equipo_cursor]
                )
                cur_eq = equipo_cursor.getvalue()
                cols_eq = [col[0] for col in cur_eq.description]
                equipo_equipado = [dict(zip(cols_eq, row)) for row in cur_eq]

                inv_cursor = cursor.var(oracledb.DB_TYPE_CURSOR)
                cursor.callproc(
                    "pkg_inventario.traer_equipo_desequipado",
                    [id_personaje, inv_cursor]
                )
                cur_inv = inv_cursor.getvalue()
                cols_inv = [col[0] for col in cur_inv.description]
                inventario = [dict(zip(cols_inv, row)) for row in cur_inv]

                return jsonify({
                    "detalle": personaje_detalle,
                    "equipo": equipo_equipado,
                    "inventario": inventario
                }), 200

    except Exception as e:
        print(f"Error al traer detalle de personaje: {e}")
        return jsonify({"error": str(e)}), 500