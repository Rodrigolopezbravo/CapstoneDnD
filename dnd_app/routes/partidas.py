from flask import Blueprint, render_template, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
import oracledb
import random
import re
from dnd_app import pool, socketio 

partidas_bp = Blueprint("partidas", __name__)

# --- HELPER: TIRA DADOS EN PYTHON ---
def tirar_dados_python(formula):
    try:
        if not formula: return 0
        match = re.match(r'(\d+)d(\d+)(?:\+(\d+))?', formula.lower().replace(" ", ""))
        if match:
            n, c, b = int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)
            return sum(random.randint(1, c) for _ in range(n)) + b
        return int(formula) if formula.isdigit() else 0
    except: return 0

# ==========================================
# GESTIÓN DE PARTIDA
# ==========================================

@partidas_bp.route("/create", methods=["POST"])
@jwt_required()
def crear_partida():
    data = request.get_json()
    id_personaje, nombre_partida = data.get("id_personaje"), data.get("nombre_partida")
    try:
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                cursor.callproc("pkg_partida.crear_partida", [nombre_partida, id_personaje])
                cursor.execute("SELECT MAX(id_partida) FROM participacion WHERE id_personaje = :1 AND rol = 'host'", [id_personaje])
                row = cursor.fetchone()
                if row and row[0]:
                    pid = row[0]
                    cursor.callproc("pkg_turnos.iniciar_turnos", [pid])
                    cursor.execute("""
                        UPDATE turno_partida SET acciones_totales = (SELECT COUNT(*) FROM participacion WHERE id_partida=:1 AND rol!='dm'),
                        acciones_restantes = (SELECT COUNT(*) FROM participacion WHERE id_partida=:1 AND rol!='dm') WHERE id_partida=:1
                    """, [pid])
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
                cursor.execute("SELECT id_partida FROM partida WHERE codigo = :1", [data.get("codigo")])
                row = cursor.fetchone()
                if row and row[0]:
                    pid = row[0]
                    cursor.callproc("pkg_turnos.iniciar_turnos", [pid])
                    cursor.execute("""
                        UPDATE turno_partida SET acciones_totales = (SELECT COUNT(*) FROM participacion WHERE id_partida=:1 AND rol!='dm'),
                        acciones_restantes = (SELECT COUNT(*) FROM participacion WHERE id_partida=:1 AND rol!='dm') WHERE id_partida=:1
                    """, [pid])
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
                    data.append({"id": r[2], "personaje": r[3], "clase": r[4], "hp_actual": curr, "hp_max": maxx, "porcentaje": int(pct)})
        return jsonify(data), 200
    except Exception: return jsonify([]), 200

@partidas_bp.route("/tablero/monstruos/<int:id_partida>", methods=["GET"])
@jwt_required()
def traer_monstruos(id_partida):
    try:
        monstruos = []
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT ROWIDTOCHAR(em.rowid), m.nombre, em.x, em.y, m.id_monstruo FROM encuentro_monstruo em JOIN encuentro e ON em.id_encuentro=e.id_encuentro JOIN monstruo m ON em.id_monstruo=m.id_monstruo WHERE e.id_partida=:1 AND em.puntos_vida_actual>0", [id_partida])
                for row in cursor:
                    monstruos.append({"id": row[0], "nombre": row[1], "x": row[2], "y": row[3], "id_real": row[4]})
        return jsonify(monstruos), 200
    except Exception: return jsonify([]), 200

# [INVENTARIO Y EQUIPO]
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
                out = c.var(oracledb.DB_TYPE_CURSOR); c.callproc(proc, [id_p, out]); cur = out.getvalue(); cols = [x[0] for x in cur.description]
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
        socketio.emit("accion_realizada", {"msg": "Equipo"}, room=f"partida_{d.get('id_partida')}")
        return jsonify({"status": "ok"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 400

# ==========================================
# 4. COMBATE (ATAQUE FÍSICO)
# ==========================================
@partidas_bp.route("/accion/atacar", methods=["POST"])
@jwt_required()
def accion_atacar():
    d = request.get_json()
    rowid_objetivo, id_partida, id_personaje = d.get("id_objetivo"), d.get("id_partida"), int(d.get("id_personaje"))
    try:
        combate_terminado = False
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT count(*) FROM inventario i JOIN equipo e ON i.id_equipo=e.id_equipo WHERE i.id_personaje=:1 AND i.equipado=1 AND lower(e.tipo_equipo)='arma'", [id_personaje])
                tiene_arma = cursor.fetchone()[0] > 0
                usar_pkg, id_monstruo_real = False, None
                if rowid_objetivo and tiene_arma:
                    cursor.execute("SELECT id_monstruo FROM encuentro_monstruo WHERE rowid = CHARTOROWID(:1)", [rowid_objetivo])
                    row = cursor.fetchone()
                    if row: 
                        id_monstruo_real = row[0]
                        cursor.execute("SELECT count(*) FROM encuentro_monstruo em WHERE em.id_monstruo=:1 AND em.id_encuentro=(SELECT MAX(e.id_encuentro) FROM encuentro e JOIN participacion p ON p.id_partida=e.id_partida WHERE p.id_personaje=:2)", [id_monstruo_real, id_personaje])
                        if cursor.fetchone()[0] > 0: usar_pkg = True 

                exito_pkg = False
                if usar_pkg:
                    try:
                        out_cursor = cursor.var(oracledb.DB_TYPE_CURSOR)
                        cursor.callproc("pkg_acciones.atacar_con_arma", [id_personaje, id_monstruo_real, out_cursor])
                        exito_pkg = True 
                    except: exito_pkg = False
                
                if not exito_pkg:
                    cursor.execute("SELECT nombre, fuerza FROM personaje WHERE id_personaje=:1", [id_personaje])
                    pj_data = cursor.fetchone()
                    nombre_pj, mod_fuerza = pj_data[0], (pj_data[1] - 10) // 2
                    dano, nombre_arma = 1 + mod_fuerza, "sus puños"
                    cursor.execute("SELECT a.dano, e.nombre FROM inventario i JOIN equipo e ON i.id_equipo=e.id_equipo JOIN arma a ON a.id_equipo=e.id_equipo WHERE i.id_personaje=:1 AND i.equipado=1", [id_personaje])
                    row_arma = cursor.fetchone()
                    if row_arma: dano = tirar_dados_python(row_arma[0]) + mod_fuerza; nombre_arma = row_arma[1]
                    dano = max(1, dano)
                    id_encuentro_actual = None 
                    if rowid_objetivo:
                        cursor.execute("UPDATE encuentro_monstruo SET puntos_vida_actual = GREATEST(0, puntos_vida_actual - :1) WHERE rowid = CHARTOROWID(:2)", [dano, rowid_objetivo])
                        cursor.execute("SELECT id_encuentro, (SELECT nombre FROM monstruo WHERE id_monstruo=em.id_monstruo) FROM encuentro_monstruo em WHERE rowid=CHARTOROWID(:1)", [rowid_objetivo])
                        res = cursor.fetchone()
                        id_encuentro_actual = res[0] if res else None; t_name = res[1] if res else "enemigo"
                        desc = f"{nombre_pj} ataca con {nombre_arma} a {t_name} causando {dano} de daño."
                    else:
                        desc = f"{nombre_pj} ataca al aire con {nombre_arma}."
                        cursor.execute("SELECT MAX(id_encuentro) FROM encuentro WHERE id_partida=:1", [id_partida])
                        r = cursor.fetchone(); id_encuentro_actual = r[0] if r else None

                    if id_encuentro_actual:
                        cursor.execute("INSERT INTO evento(id_encuentro, id_personaje, descripcion, fecha_evento) VALUES (:1, :2, :3, SYSDATE)", [id_encuentro_actual, id_personaje, desc])
                        try: cursor.callproc("pkg_turnos.registrar_accion_jugador", [id_personaje])
                        except: pass 
                        ejecutar_contraataque(cursor, id_encuentro_actual, id_partida)

                verificar_victoria(cursor, id_partida)
                conn.commit()
        socketio.emit("accion_realizada", {"msg": "Ataque"}, room=f"partida_{id_partida}")
        return jsonify({"status": "ok"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

# ==========================================
# 5. HABILIDADES (USO DE DANO_BASE)
# ==========================================

@partidas_bp.route("/accion/habilidades/<int:id_p>", methods=["GET"])
@jwt_required()
def list_habs(id_p):
    try:
        habs = []
        with pool.acquire() as conn:
            with conn.cursor() as c:
                sql = "SELECT h.id_habilidad, h.nombre, h.tipo_efecto FROM habilidad h JOIN personaje p ON h.id_clase = p.id_clase WHERE p.id_personaje = :1 AND h.nivel_requerido <= p.nivel"
                c.execute(sql, [id_p])
                for r in c: habs.append({"id":r[0], "nombre":r[1], "tipo":r[2]})
        return jsonify(habs), 200
    except Exception as e: return jsonify({"error":str(e)}), 500

@partidas_bp.route("/accion/habilidad", methods=["POST"])
@jwt_required()
def use_hab():
    d = request.get_json()
    id_partida, id_personaje, id_habilidad = d.get("id_partida"), int(d.get("id_personaje")), int(d.get("id_habilidad"))
    objetivo_raw = d.get("id_objetivo") 
    try:
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT nombre, dano_base, tipo_efecto FROM habilidad WHERE id_habilidad=:1", [id_habilidad])
                h = cursor.fetchone()
                nombre_hab, formula, tipo = h[0], h[1], h[2]
                es_curacion = (tipo.upper() == 'CURACIÓN')
                usar_pkg, id_objetivo_pkg = False, None
                if es_curacion:
                    if objetivo_raw: id_objetivo_pkg = int(objetivo_raw); usar_pkg = True
                else:
                    if objetivo_raw:
                        cursor.execute("SELECT id_monstruo FROM encuentro_monstruo WHERE rowid = CHARTOROWID(:1)", [objetivo_raw])
                        row = cursor.fetchone()
                        if row: 
                            id_objetivo_pkg = row[0]
                            cursor.execute("SELECT count(*) FROM encuentro_monstruo em WHERE em.id_monstruo=:1 AND em.id_encuentro=(SELECT MAX(e.id_encuentro) FROM encuentro e JOIN participacion p ON p.id_partida=e.id_partida WHERE p.id_personaje=:2)", [id_objetivo_pkg, id_personaje])
                            if cursor.fetchone()[0] > 0: usar_pkg = True

                exito_pkg = False
                if usar_pkg and id_objetivo_pkg:
                    try:
                        out = cursor.var(oracledb.DB_TYPE_CURSOR)
                        cursor.callproc("pkg_acciones.atacar_con_habilidad", [id_personaje, id_habilidad, id_objetivo_pkg, out])
                        exito_pkg = True
                    except: exito_pkg = False
                
                if not exito_pkg:
                    cursor.execute("SELECT nombre FROM personaje WHERE id_personaje=:1", [id_personaje])
                    nombre_pj = cursor.fetchone()[0]
                    valor = tirar_dados_python(formula)
                    if valor == 0: valor = 1
                    id_encuentro_actual = None
                    cursor.execute("SELECT MAX(id_encuentro) FROM encuentro WHERE id_partida=:1", [id_partida])
                    r = cursor.fetchone(); id_encuentro_actual = r[0] if r else None
                    desc = ""
                    if es_curacion:
                        if objetivo_raw:
                            target_id = int(objetivo_raw)
                            cursor.execute("UPDATE personaje SET puntos_vida_actual = LEAST(puntos_vida_maximo, puntos_vida_actual + :1) WHERE id_personaje=:2", [valor, target_id])
                            cursor.execute("SELECT nombre FROM personaje WHERE id_personaje=:1", [target_id])
                            t_name = cursor.fetchone()[0]
                            desc = f"{nombre_pj} cura a {t_name} por {valor} puntos."
                        else: desc = f"{nombre_pj} lanza {nombre_hab} al aire (curación fallida)."
                    else:
                        if objetivo_raw:
                            cursor.execute("UPDATE encuentro_monstruo SET puntos_vida_actual = GREATEST(0, puntos_vida_actual - :1) WHERE rowid=CHARTOROWID(:2)", [valor, objetivo_raw])
                            cursor.execute("SELECT nombre FROM monstruo m JOIN encuentro_monstruo em ON m.id_monstruo=em.id_monstruo WHERE em.rowid=CHARTOROWID(:1)", [objetivo_raw])
                            res = cursor.fetchone(); t_name = res[0] if res else "enemigo"
                            desc = f"{nombre_pj} lanza {nombre_hab} a {t_name} causando {valor} de daño."
                        else: desc = f"{nombre_pj} lanza {nombre_hab} al aire."
                    
                    if id_encuentro_actual:
                        cursor.execute("INSERT INTO evento(id_encuentro, id_personaje, descripcion, fecha_evento) VALUES (:1, :2, :3, SYSDATE)", [id_encuentro_actual, id_personaje, desc])
                        try: cursor.callproc("pkg_turnos.registrar_accion_jugador", [id_personaje])
                        except: pass
                        if not es_curacion: ejecutar_contraataque(cursor, id_encuentro_actual, id_partida)

                verificar_victoria(cursor, id_partida)
                conn.commit()
        socketio.emit("accion_realizada", {"msg": "Habilidad"}, room=f"partida_{id_partida}")
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

# --- HELPERS INTERNOS ---
def ejecutar_contraataque(cursor, id_encuentro, id_partida):
    cursor.execute("SELECT em.id_monstruo, m.nombre FROM encuentro_monstruo em JOIN monstruo m ON em.id_monstruo=m.id_monstruo WHERE em.id_encuentro = :1 AND em.puntos_vida_actual > 0", [id_encuentro])
    monstruos_vivos = cursor.fetchall()
    if monstruos_vivos:
        cursor.execute("SELECT p.id_personaje, p.nombre FROM personaje p JOIN participacion pa ON p.id_personaje = pa.id_personaje WHERE pa.id_partida = :1 AND p.puntos_vida_actual > 0 AND pa.rol = 'jugador' ORDER BY dbms_random.value FETCH FIRST 1 ROWS ONLY", [id_partida])
        target_pj = cursor.fetchone()
        if target_pj:
            for mon in monstruos_vivos:
                dano_mon = random.randint(1, 6)
                cursor.execute("UPDATE personaje SET puntos_vida_actual = GREATEST(0, puntos_vida_actual - :1) WHERE id_personaje=:2", [dano_mon, target_pj[0]])
                desc_mon = f"El enemigo {mon[1]} contraataca a {target_pj[1]} infligiendo {dano_mon} de daño."
                cursor.execute("INSERT INTO evento(id_encuentro, id_monstruo, id_personaje, descripcion, fecha_evento) VALUES (:1, :2, :3, :4, SYSDATE)", [id_encuentro, mon[0], target_pj[0], desc_mon])

def verificar_victoria(cursor, id_partida):
    cursor.execute("SELECT count(*) FROM encuentro_monstruo em JOIN encuentro e ON e.id_encuentro=em.id_encuentro WHERE e.id_partida=:1 AND em.puntos_vida_actual > 0", [id_partida])
    if cursor.fetchone()[0] == 0:
        cursor.execute("SELECT MAX(id_encuentro) FROM encuentro WHERE id_partida=:1", [id_partida])
        id_enc = cursor.fetchone()[0]
        cursor.execute("SELECT count(*) FROM evento WHERE id_encuentro=:1 AND descripcion LIKE '%COMBATE_FINALIZADO%'", [id_enc])
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO evento(id_encuentro, descripcion, fecha_evento) VALUES (:1, '[[SISTEMA]] COMBATE_FINALIZADO', SYSDATE)", [id_enc])
            from dnd_app.routes.chat import trigger_post_combat
            socketio.start_background_task(trigger_post_combat, id_partida, f"partida_{id_partida}")