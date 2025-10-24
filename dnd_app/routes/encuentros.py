from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from dnd_app import combat

encuentros_bp = Blueprint("encuentros", __name__)

@encuentros_bp.route("/<int:partida_id>/create", methods=["POST"])
@jwt_required()
def crear_encuentro(partida_id):
    user_id = get_jwt_identity()
    data = request.get_json()
    nombre = data.get("nombre", "Encuentro")
    kind = data.get("kind", "combate")
    difficulty = data.get("difficulty", 1)
    # verificar acceso: el usuario debe tener personaje en la partida si no es system
    acceso = Personaje.query.filter_by(usuario_id=user_id, partida_id=partida_id).first()
    if not acceso:
        return jsonify({"error":"no tienes acceso"}), 403
    enc = Encuentro(partida_id=partida_id, nombre=nombre, kind=kind, difficulty=difficulty, description=data.get("description",""))
    db.session.add(enc)
    db.session.commit()
    # log evento
    evt = GameEvent(partida_id=partida_id, event_type="encounter_created", description=f"Encuentro '{nombre}' creado")
    db.session.add(evt)
    db.session.commit()
    return jsonify({"message":"encuentro creado","id":enc.id}), 201

@encuentros_bp.route("/<int:partida_id>/resolve", methods=["POST"])
@jwt_required()
def resolver_encuentro(partida_id):
    user_id = get_jwt_identity()
    data = request.get_json()
    acciones = data.get("acciones", [])
    resultados = []
    partida = Partida.query.get_or_404(partida_id)
    # check access
    acceso = Personaje.query.filter_by(usuario_id=user_id, partida_id=partida_id).first()
    if not acceso:
        return jsonify({"error":"no tienes acceso"}), 403

    # item_lookup helper: devuelve diccionario simple del item
    def item_lookup(item_id):
        from dnd_app.models import Item
        it = Item.query.get(item_id)
        if not it:
            return None
        return {"id":it.id, "nombre":it.nombre, "bonos": it.bonos or {}}

    for a in acciones:
        pid = a.get("personaje_id")
        accion = a.get("accion")
        p = Personaje.query.get(pid)
        if not p or p.partida_id != partida_id:
            resultados.append({"error": f"personaje {pid} no válido"})
            continue
        if p.estado != "activo" and accion != "ver":
            resultados.append({"personaje": p.id, "msg":"no activo, no puede actuar"})
            continue

        if accion == "atacar":
            target_id = a.get("target_id")
            tipo = a.get("tipo","melee")
            t = Personaje.query.get(target_id)
            if not t or t.partida_id != partida_id:
                resultados.append({"error": "target inválido"})
                continue
            res = combat.resolver_ataque(p, t, tipo, item_lookup)
            # crear evento
            desc = f"{p.nombre} atacó a {t.nombre}: { 'CRÍTICO ' if res['critico'] else ''}{'PIFIA' if res['pifia'] else ''} daño {res.get('dano',0)}"
            evt = GameEvent(partida_id=partida_id, personaje_id=p.id, event_type="attack", description=desc, xp_gain=0)
            db.session.add(evt)
            db.session.commit()
            resultados.append(res)

        elif accion == "huir":
            ok, info = combat.intento_huir(p, dc=15)
            if ok:
                # queda en estado waiting / marchandose (especificamos)
                p.estado = "spectator"  # o "waiting"
                evt = GameEvent(partida_id=partida_id, personaje_id=p.id, event_type="flee_success", description=f"{p.nombre} huyó con éxito")
                db.session.add(evt)
                db.session.commit()
                resultados.append({"personaje":p.id,"accion":"huir","ok":True,"info":info})
            else:
                # falla y forzado a pelear: marcamos su estado activo pero registramos evento
                evt = GameEvent(partida_id=partida_id, personaje_id=p.id, event_type="flee_fail", description=f"{p.nombre} falló en huir y debe pelear")
                db.session.add(evt)
                db.session.commit()
                resultados.append({"personaje":p.id,"accion":"huir","ok":False,"info":info})

        elif accion == "dialogar":
            # tirar d20 + CHA + INT/2
            from dnd_app.combat import tirar_dado
            roll = tirar_dado(20) + p.mod(p.carisma if False else p.carisma) # placeholder
            # For simplicity, implement as success if >=12
            if roll >= 12:
                evt = GameEvent(partida_id=partida_id, personaje_id=p.id, event_type="dialog_success", description=f"{p.nombre} consiguió dialogar (roll {roll})")
                db.session.add(evt)
                db.session.commit()
                resultados.append({"personaje":p.id,"accion":"dialogar","ok":True,"roll":roll})
            else:
                evt = GameEvent(partida_id=partida_id, personaje_id=p.id, event_type="dialog_fail", description=f"{p.nombre} falló dialogando (roll {roll})")
                db.session.add(evt)
                db.session.commit()
                resultados.append({"personaje":p.id,"accion":"dialogar","ok":False,"roll":roll})

        elif accion == "esperar":
            # efecto: sumaremos un evento y damos ventaja la siguiente ronda (simplificado)
            evt = GameEvent(partida_id=partida_id, personaje_id=p.id, event_type="wait", description=f"{p.nombre} espera defensivamente")
            db.session.add(evt)
            db.session.commit()
            resultados.append({"personaje":p.id,"accion":"esperar","ok":True})

        else:
            resultados.append({"error":"accion desconocida"})
    return jsonify({"resultados":resultados})
