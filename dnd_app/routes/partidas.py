from flask import Blueprint, render_template, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
import oracledb
import random # Para los dados en el fallback
from dnd_app import pool, socketio 

partidas_bp = Blueprint("partidas", __name__)

# ==========================================
# 1. GESTIÓN DE PARTIDA
# ==========================================

@partidas_bp.route("/create", methods=["POST"])
@jwt_required()
def crear_partida():
    data = request.get_json()
    try:
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                cursor.callproc("pkg_partida.crear_partida", [data.get("nombre_partida"), data.get("id_personaje")])
                conn.commit()
        return jsonify({"message": "Creada"}), 201
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
                out = cursor.var(oracledb.NUMBER)
                cursor.callproc("pkg_partida.obtener_partida_por_personaje", [id_personaje, out])
                val = out.getvalue()
                if val: return jsonify({"status": "en_partida", "id_partida": int(val)}), 200
                return jsonify({"status": "sin_partida"}), 200
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
                if not row: return "No existe", 404
                partida = {"id": row[0], "nombre": row[1], "codigo": row[5]}
                
                uid = int(get_jwt_identity())
                out_p = cursor.var(oracledb.DB_TYPE_CURSOR)
                cursor.callproc("pkg_partida.traer_jugadores_partida", [id_partida, out_p])
                pid = next((int(r[2]) for r in out_p.getvalue() if int(r[0]) == uid), None)
                
                if pid is None: return "Error: No tienes personaje en esta partida", 400

        return render_template("partida.html", partida=partida, id_personaje=pid, id_usuario=uid)
    except Exception as e: return str(e), 500

# ==========================================
# 2. DATOS DEL TABLERO
# ==========================================

@partidas_bp.route("/jugadores/<int:id_partida>")
@jwt_required()
def traer_jugadores(id_partida):
    try:
        data = []
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                out = cursor.var(oracledb.DB_TYPE_CURSOR)
                cursor.callproc("pkg_partida.traer_jugadores_partida", [id_partida, out])
                for r in out.getvalue():
                    curr = r[5] if r[5] is not None else 10
                    maxx = r[6] if r[6] is not None else 10
                    pct = (curr/maxx)*100 if maxx > 0 else 0
                    data.append({
                        "personaje": r[3], "clase": r[4], 
                        "hp_actual": curr, "hp_max": maxx, "porcentaje": int(pct)
                    })
        return jsonify(data), 200
    except Exception: return jsonify([]), 200

@partidas_bp.route("/tablero/monstruos/<int:id_partida>", methods=["GET"])
@jwt_required()
def traer_monstruos(id_partida):
    try:
        monstruos = []
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                sql = """
                    SELECT ROWIDTOCHAR(em.rowid), m.nombre, em.x, em.y
                    FROM encuentro_monstruo em
                    JOIN encuentro e ON em.id_encuentro = e.id_encuentro
                    JOIN monstruo m ON em.id_monstruo = m.id_monstruo
                    WHERE e.id_partida = :1 AND em.puntos_vida_actual > 0
                """
                cursor.execute(sql, [id_partida])
                for row in cursor:
                    monstruos.append({"id": row[0], "nombre": row[1], "x": row[2], "y": row[3]})
        return jsonify(monstruos), 200
    except Exception as e:
        return jsonify([]), 200

# ==========================================
# 3. INVENTARIO Y EQUIPO
# ==========================================

@partidas_bp.route("/equipo/<int:id_p>", methods=["GET"])
@jwt_required()
def get_equipo(id_p): return _get_items("pkg_inventario.traer_equipo_equipado", id_p)

@partidas_bp.route("/inventario/<int:id_p>", methods=["GET"])
@jwt_required()
def get_inv(id_p): return _get_items("pkg_inventario.traer_equipo_desequipado", id_p)

def _get_items(proc, id_p):
    try:
        with pool.acquire() as conn:
            with conn.cursor() as c:
                out = c.var(oracledb.DB_TYPE_CURSOR)
                c.callproc(proc, [id_p, out])
                cur = out.getvalue()
                cols = [x[0] for x in cur.description]
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
            with conn.cursor() as c:
                c.callproc(f"pkg_acciones.{accion}_objeto", [int(d.get("id_personaje")), int(d.get("id_objeto"))])
            conn.commit()
        return jsonify({"status": "ok"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 400

# ==========================================
# 4. COMBATE (BLINDADO CONTRA ERRORES DE SQL)
# ==========================================

@partidas_bp.route("/accion/atacar", methods=["POST"])
@jwt_required()
def accion_atacar():
    d = request.get_json()
    rowid_objetivo = d.get("id_objetivo")
    id_partida = d.get("id_partida")
    id_personaje = int(d.get("id_personaje"))
    
    try:
        combate_terminado = False
        
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                
                # --- INTENTO 1: VÍA PAQUETE SQL ---
                try:
                    id_monstruo_real = 1
                    if rowid_objetivo:
                        cursor.execute("SELECT id_monstruo FROM encuentro_monstruo WHERE rowid = CHARTOROWID(:1)", [rowid_objetivo])
                        row = cursor.fetchone()
                        if row: id_monstruo_real = row[0]
                    
                    out_cursor = cursor.var(oracledb.DB_TYPE_CURSOR)
                    cursor.callproc("pkg_acciones.atacar_con_arma", [id_personaje, id_monstruo_real, out_cursor])
                
                # --- INTENTO 2: FALLBACK MANUAL EN PYTHON (SI SQL FALLA) ---
                except Exception as db_err:
                    print(f"⚠️ Fallo en pkg_acciones, usando Fallback Python: {db_err}")
                    
                    # 1. Obtener Nombre PJ
                    cursor.execute("SELECT nombre FROM personaje WHERE id_personaje=:1", [id_personaje])
                    nombre_pj = cursor.fetchone()[0]
                    
                    # 2. Calcular daño simple (1d8 + 2 por ejemplo)
                    dano = random.randint(1, 8) + 2
                    target_name = "al aire"

                    # 3. Si hay objetivo, restar vida manualmente
                    if rowid_objetivo:
                        # Obtener nombre monstruo
                        cursor.execute("""
                            SELECT m.nombre FROM encuentro_monstruo em 
                            JOIN monstruo m ON m.id_monstruo=em.id_monstruo 
                            WHERE em.rowid=CHARTOROWID(:1)
                        """, [rowid_objetivo])
                        t_row = cursor.fetchone()
                        if t_row: target_name = t_row[0]

                        # UPDATE directo
                        cursor.execute("""
                            UPDATE encuentro_monstruo 
                            SET puntos_vida_actual = GREATEST(0, puntos_vida_actual - :1) 
                            WHERE rowid = CHARTOROWID(:2)
                        """, [dano, rowid_objetivo])
                    
                    # 4. Obtener ID Encuentro
                    cursor.execute("""
                        SELECT MAX(id_encuentro) FROM encuentro WHERE id_partida=:1
                    """, [id_partida])
                    id_encuentro = cursor.fetchone()[0]

                    # 5. Insertar evento manualmente
                    cursor.execute("""
                        INSERT INTO evento(id_encuentro, id_personaje, descripcion, fecha_evento)
                        VALUES (:1, :2, :3, SYSDATE)
                    """, [id_encuentro, id_personaje, f"{nombre_pj} ataca a {target_name} (Manual: {dano} daño)"])
                
                # --- VERIFICACIÓN DE VICTORIA (COMÚN PARA AMBOS MÉTODOS) ---
                cursor.execute("""
                    SELECT count(*) FROM encuentro_monstruo 
                    em JOIN encuentro e ON e.id_encuentro=em.id_encuentro
                    WHERE e.id_partida=:1 AND em.puntos_vida_actual > 0
                """, [id_partida])
                vivos = cursor.fetchone()[0]
                
                if vivos == 0:
                    combate_terminado = True
                    # Insertar marca de fin si no existe
                    cursor.execute("""
                        INSERT INTO evento(id_encuentro, descripcion, fecha_evento)
                        VALUES ((SELECT MAX(id_encuentro) FROM encuentro WHERE id_partida=:1), '[[SISTEMA]] COMBATE_FINALIZADO', SYSDATE)
                    """, [id_partida])

                conn.commit()
        
        # Notificar
        socketio.emit("accion_realizada", {"msg": "Ataque"}, room=f"partida_{id_partida}")
        
        if combate_terminado:
            socketio.emit("combate_terminado", {"msg": "Victoria"}, room=f"partida_{id_partida}")
            from dnd_app.routes.chat import trigger_post_combat
            socketio.start_background_task(trigger_post_combat, id_partida, f"partida_{id_partida}")

        return jsonify({"status": "ok"}), 200

    except Exception as e: 
        print(f"❌ Error Crítico Ataque: {e}")
        return jsonify({"error": str(e)}), 500

@partidas_bp.route("/accion/habilidades/<int:id_p>", methods=["GET"])
@jwt_required()
def list_habs(id_p):
    try:
        habs = []
        with pool.acquire() as conn:
            with conn.cursor() as c:
                sql="SELECT h.id_habilidad, h.nombre FROM habilidad h JOIN clase_habilidad ch ON h.id_habilidad=ch.id_habilidad JOIN personaje p ON p.id_clase=ch.id_clase WHERE p.id_personaje=:1"
                c.execute(sql, [id_p])
                for r in c: habs.append({"id":r[0], "nombre":r[1]})
        return jsonify(habs), 200
    except Exception as e: return jsonify({"error":str(e)}), 500

@partidas_bp.route("/accion/habilidad", methods=["POST"])
@jwt_required()
def use_hab():
    d = request.get_json()
    try:
        with pool.acquire() as conn:
            with conn.cursor() as c:
                out = c.var(oracledb.DB_TYPE_CURSOR)
                c.callproc("pkg_acciones.atacar_con_habilidad", [int(d.get("id_personaje")), int(d.get("id_habilidad")), 1, out])
                conn.commit()
        socketio.emit("accion_realizada", {"msg": "Habilidad"}, room=f"partida_{d.get('id_partida')}")
        return jsonify({"status": "ok"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@partidas_bp.route("/accion/consumibles/<int:id_p>", methods=["GET"])
@jwt_required()
def list_cons(id_p):
    try:
        items = []
        with pool.acquire() as conn:
            with conn.cursor() as c:
                sql="SELECT i.id_equipo, e.nombre, i.cantidad FROM inventario i JOIN equipo e ON i.id_equipo=e.id_equipo JOIN consumible c ON c.id_equipo=e.id_equipo WHERE i.id_personaje=:1 AND i.cantidad>0"
                c.execute(sql, [id_p])
                for r in c: items.append({"id":r[0], "nombre":r[1], "cantidad":r[2]})
        return jsonify(items), 200
    except Exception as e: return jsonify({"error":str(e)}), 500

@partidas_bp.route("/accion/pocion", methods=["POST"])
@jwt_required()
def use_pot():
    d = request.get_json()
    try:
        with pool.acquire() as conn:
            with conn.cursor() as c:
                c.callproc("pkg_acciones.usar_pocion", [d.get("id_personaje"), d.get("id_objeto")])
                conn.commit()
        socketio.emit("accion_realizada", {"msg": "Pocion"}, room=f"partida_{d.get('id_partida')}")
        return jsonify({"status": "ok"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500