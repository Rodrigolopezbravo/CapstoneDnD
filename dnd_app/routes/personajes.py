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

# =====================================================================
# Traer detalles de UN personaje específico (¡NUEVA FUNCIÓN!)
# =====================================================================
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
                columnas = [col[0] for col in result_cursor.description]
                
                personaje_detalle = {}
                personaje_inventario = []
                primera_fila = True

                # Recorremos TODAS las filas que devuelve el cursor
                for row in result_cursor:
                    fila_dict = dict(zip(columnas, row))

                    # La primera fila la usamos para sacar los detalles del personaje
                    if primera_fila:
                        personaje_detalle = fila_dict.copy() # Copiamos los datos
                        primera_fila = False
                    
                    # De cada fila (incluida la primera), extraemos el item
                    if fila_dict.get("NOMBRE_EQUIPO"):
                        personaje_inventario.append({
                            "NOMBRE": fila_dict.get("NOMBRE_EQUIPO"),
                            "CANTIDAD": fila_dict.get("CANTIDAD")
                        })

                if not personaje_detalle:
                    return jsonify({"error": "Personaje no encontrado o no te pertenece"}), 404
                
                # Limpiamos los datos del item del objeto 'detalle'
                personaje_detalle.pop("NOMBRE_EQUIPO", None)
                personaje_detalle.pop("CANTIDAD", None)

                # Devolvemos todo en un solo JSON estructurado
                return jsonify({
                    "detalle": personaje_detalle,
                    "inventario": personaje_inventario
                }), 200

    except Exception as e:
        print(f"Error al traer detalle de personaje: {e}")
        return jsonify({"error": str(e)}), 500