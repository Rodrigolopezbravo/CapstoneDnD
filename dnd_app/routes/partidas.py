from flask import Blueprint, render_template, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
import oracledb
# Importamos pool Y socketio (necesario para avisar del ataque)
from dnd_app import pool, socketio 

partidas_bp = Blueprint("partidas", __name__)

# ==========================================
# 1. GESTIÓN DE PARTIDA Y SALA
# ==========================================

@partidas_bp.route("/create", methods=["POST"])
@jwt_required()
def crear_partida():
    data = request.get_json()
    personaje_id = data.get("id_personaje")
    nombre = data.get("nombre_partida", "")
    if not personaje_id or not nombre: return jsonify({"error": "Faltan datos"}), 400
    try:
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                cursor.callproc("pkg_partida.crear_partida", [nombre, personaje_id])
                conn.commit()
        return jsonify({"message": "Partida creada"}), 201
    except Exception as e: return jsonify({"error": str(e)}), 500

@partidas_bp.route("/join", methods=["POST"])
@jwt_required()
def unirse_partida():
    data = request.get_json()
    try:
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                cursor.callproc("pkg_partida.unir_a_partida", [data.get("codigo"), data.get("id_personaje")])
            conn.commit()
        return jsonify({"message": "Unido"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@partidas_bp.route("/ir/<int:id_personaje>", methods=["GET"])
@jwt_required()
def ir_a_partida(id_personaje):
    try:
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                out_id = cursor.var(oracledb.NUMBER)
                cursor.callproc("pkg_partida.obtener_partida_por_personaje", [id_personaje, out_id])
                p = out_id.getvalue()
                if p: return jsonify({"status": "en_partida", "id_partida": int(p)}), 200
                else: return jsonify({"status": "sin_partida"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@partidas_bp.route("/partida/<int:id_partida>")
@jwt_required()
def ver_partida(id_partida):
    try:
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                out = cursor.var(oracledb.DB_TYPE_CURSOR)
                cursor.callproc("pkg_partida.traer_partida_por_id", [id_partida, out])
                row = out.getvalue().fetchone()
                if not row: return "Partida no existe", 404
                partida = {"id": row[0], "nombre": row[1], "codigo": row[5]}
                
                uid = int(get_jwt_identity())
                out_p = cursor.var(oracledb.DB_TYPE_CURSOR)
                cursor.callproc("pkg_partida.traer_jugadores_partida", [id_partida, out_p])
                pid = next((int(j[2]) for j in out_p.getvalue() if int(j[0]) == uid), None)
                if pid is None: return jsonify({"error": "No tienes personaje aquí"}), 400

        return render_template("partida.html", partida=partida, id_personaje=pid, id_usuario=uid)
    except Exception as e: return jsonify({"error": str(e)}), 500

# ==========================================
# 2. DATOS DEL TABLERO (JUGADORES Y MONSTRUOS)
# ==========================================

@partidas_bp.route("/jugadores/<int:id_partida>")
@jwt_required()
def traer_jugadores(id_partida):
    try:
        jugadores = []
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                out = cursor.var(oracledb.DB_TYPE_CURSOR)
                cursor.callproc("pkg_partida.traer_jugadores_partida", [id_partida, out])
                for r in out.getvalue():
                    hpa = r[5] if r[5] is not None else 10
                    hpm = r[6] if r[6] is not None else 10
                    pct = (hpa/hpm)*100 if hpm > 0 else 0
                    jugadores.append({
                        "id_usuario": r[0], "usuario": r[1],
                        "id_personaje": r[2], "personaje": r[3], "clase": r[4],
                        "hp_actual": hpa, "hp_max": hpm, "porcentaje": int(pct)
                    })
        return jsonify(jugadores), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@partidas_bp.route("/tablero/monstruos/<int:id_partida>", methods=["GET"])
@jwt_required()
def traer_monstruos_tablero(id_partida):
    """ CORREGIDO CON ROWID PARA EVITAR ERROR 500 """
    try:
        monstruos = []
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                sql = """
                    SELECT ROWIDTOCHAR(em.rowid) as id_seguro, m.nombre, em.x, em.y
                    FROM encuentro_monstruo em
                    JOIN encuentro e ON em.id_encuentro = e.id_encuentro
                    JOIN monstruo m ON em.id_monstruo = m.id_monstruo
                    WHERE e.id_partida = :1
                      AND em.puntos_vida_actual > 0
                """
                cursor.execute(sql, [id_partida])
                for row in cursor:
                    monstruos.append({
                        "id": row[0], "nombre": row[1], "x": row[2], "y": row[3]
                    })
        return jsonify(monstruos), 200
    except Exception as e:
        print(f"❌ ERROR SQL MONSTRUOS: {e}") 
        return jsonify({"error": str(e)}), 500

# ==========================================
# 3. INVENTARIO Y EQUIPO
# ==========================================

@partidas_bp.route("/equipo/<int:id_personaje>", methods=["GET"])
@jwt_required()
def traer_equipo(id_personaje):
    try:
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                out = cursor.var(oracledb.DB_TYPE_CURSOR)
                cursor.callproc("pkg_inventario.traer_equipo_equipado", [id_personaje, out])
                cur = out.getvalue()
                cols = [c[0] for c in cur.description]
                return jsonify([dict(zip(cols, row)) for row in cur]), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@partidas_bp.route("/inventario/<int:id_personaje>", methods=["GET"])
@jwt_required()
def traer_inventario(id_personaje):
    try:
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                out = cursor.var(oracledb.DB_TYPE_CURSOR)
                cursor.callproc("pkg_inventario.traer_equipo_desequipado", [id_personaje, out])
                cur = out.getvalue()
                cols = [c[0] for c in cur.description]
                return jsonify([dict(zip(cols, row)) for row in cur]), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@partidas_bp.route("/equipo/equipar", methods=["POST"])
@jwt_required()
def equipar_objeto(): return accion_objeto("equipar")

@partidas_bp.route("/equipo/desequipar", methods=["POST"])
@jwt_required()
def desequipar_objeto(): return accion_objeto("desequipar")

def accion_objeto(accion):
    d = request.get_json()
    try:
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                proc = f"pkg_acciones.{accion}_objeto"
                cursor.callproc(proc, [d.get("id_personaje"), d.get("id_objeto")])
            conn.commit()
        return jsonify({"status": "ok"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 400

# ==========================================
# 4. NUEVO: ACCIONES DE COMBATE (pkg_acciones)
# ==========================================

# ATACAR (Básico)
@partidas_bp.route("/accion/atacar", methods=["POST"])
@jwt_required()
def accion_atacar():
    d = request.get_json()
    try:
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                cursor.callproc("pkg_acciones.atacar_con_arma", [d.get("id_personaje")])
                conn.commit()
        
        # Avisar a todos para ver el daño en el chat
        socketio.emit("accion_realizada", {"msg": "Ataque"}, room=f"partida_{d.get('id_partida')}")
        return jsonify({"status": "ok"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

# LISTAR HABILIDADES (Para el menú)
@partidas_bp.route("/accion/habilidades/<int:id_personaje>", methods=["GET"])
@jwt_required()
def listar_habilidades(id_personaje):
    try:
        habs = []
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                sql = """SELECT h.id_habilidad, h.nombre, h.descripcion FROM habilidad h
                         JOIN clase_habilidad ch ON h.id_habilidad = ch.id_habilidad
                         JOIN personaje p ON p.id_clase = ch.id_clase WHERE p.id_personaje = :1"""
                cursor.execute(sql, [id_personaje])
                for r in cursor: habs.append({"id":r[0], "nombre":r[1]})
        return jsonify(habs), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

# USAR HABILIDAD
@partidas_bp.route("/accion/habilidad", methods=["POST"])
@jwt_required()
def usar_habilidad():
    d = request.get_json()
    try:
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                cursor.callproc("pkg_acciones.atacar_con_habilidad", [d.get("id_personaje"), d.get("id_habilidad")])
                conn.commit()
        socketio.emit("accion_realizada", {"msg": "Habilidad"}, room=f"partida_{d.get('id_partida')}")
        return jsonify({"status": "ok"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

# LISTAR CONSUMIBLES (Para el menú de pociones)
@partidas_bp.route("/accion/consumibles/<int:id_personaje>", methods=["GET"])
@jwt_required()
def listar_consumibles(id_personaje):
    try:
        items = []
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                sql = """SELECT i.id_equipo, e.nombre, i.cantidad FROM inventario i
                         JOIN equipo e ON i.id_equipo = e.id_equipo
                         JOIN consumible c ON c.id_equipo = e.id_equipo
                         WHERE i.id_personaje = :1 AND i.cantidad > 0"""
                cursor.execute(sql, [id_personaje])
                for r in cursor: items.append({"id":r[0], "nombre":r[1], "cantidad":r[2]})
        return jsonify(items), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

# USAR POCION
@partidas_bp.route("/accion/pocion", methods=["POST"])
@jwt_required()
def usar_pocion():
    d = request.get_json()
    try:
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                cursor.callproc("pkg_acciones.usar_pocion", [d.get("id_personaje"), d.get("id_objeto")])
                conn.commit()
        socketio.emit("accion_realizada", {"msg": "Pocion"}, room=f"partida_{d.get('id_partida')}")
        return jsonify({"status": "ok"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500