from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from dnd_app import db
from dnd_app.models import Personaje, Usuario, Item, Partida, GameEvent
from dnd_app.combat import intento_huir, calcular_xp

personajes_bp = Blueprint("personajes", __name__)

@personajes_bp.route("/create", methods=["POST"])
@jwt_required()
def crear_personaje():
    user_id = get_jwt_identity()
    data = request.get_json()
    nombre = data.get("nombre")
    if not nombre:
        return jsonify({"error":"nombre requerido"}), 400
    # stats opcionales
    stats = {
        "fuerza": data.get("fuerza", 10),
        "destreza": data.get("destreza", 10),
        "constitucion": data.get("constitucion", 10),
        "inteligencia": data.get("inteligencia", 10),
        "sabiduria": data.get("sabiduria", 10),
        "carisma": data.get("carisma", 10),
        "agilidad": data.get("agilidad", 10)
    }
    vida_max = 10 + ((stats["constitucion"] - 10)//2)*1
    p = Personaje(nombre=nombre, usuario_id=user_id, vida_max=vida_max, vida_actual=vida_max, **stats)
    db.session.add(p)
    db.session.commit()
    return jsonify({"message":"Personaje creado", "id": p.id}), 201

@personajes_bp.route("/my", methods=["GET"])
@jwt_required()
def my_personajes():
    user_id = get_jwt_identity()
    ps = Personaje.query.filter_by(usuario_id=user_id).all()
    out = []
    for p in ps:
        out.append({"id":p.id,"nombre":p.nombre,"nivel":p.nivel,"vida":p.vida_actual,"estado":p.estado,"partida_id":p.partida_id})
    return jsonify(out)

# equipar (slot simple: casco, armadura, guante, botas, anillo1, anillo2, amuleto, arma_melee, arma_ranged, offhand)
@personajes_bp.route("/<int:pid>/equip", methods=["POST"])
@jwt_required()
def equipar(pid):
    user_id = get_jwt_identity()
    p = Personaje.query.get_or_404(pid)
    if p.usuario_id != user_id:
        return jsonify({"error":"no autorizado"}), 403
    data = request.get_json()
    slot = data.get("slot")
    item_id = data.get("item_id")
    item = Item.query.get(item_id)
    if not item:
        return jsonify({"error":"item no existe"}), 404
    # check restrictions if any
    restricciones = item.restricciones or []
    if restricciones and p.usuario_id: # aquí en realidad sería por clase del personaje; simplificamos
        # skip check for now
        pass
    # equipar: guardar id en equipo JSON
    eq = p.equipo or {}
    eq[slot] = item.id
    p.equipo = eq
    db.session.commit()
    return jsonify({"message":"equipado", "slot":slot, "item":item.nombre})

# unir personaje a partida
@personajes_bp.route("/<int:pid>/join/<int:partida_id>", methods=["POST"])
@jwt_required()
def join_partida(pid, partida_id):
    user_id = get_jwt_identity()
    p = Personaje.query.get_or_404(pid)
    if p.usuario_id != user_id:
        return jsonify({"error":"no autorizado"}), 403
    if p.partida_id:
        return jsonify({"error":"personaje ya en otra partida"}), 400
    partida = Partida.query.get(partida_id)
    if not partida:
        return jsonify({"error":"partida no existe"}), 404
    p.partida_id = partida_id
    db.session.commit()
    # evento join
    evt = GameEvent(partida_id=partida_id, personaje_id=p.id, event_type="join", description=f"{p.nombre} se unió")
    db.session.add(evt)
    db.session.commit()
    return jsonify({"message":"personaje unido a partida"})

# eliminar => marcar espectador (cuando muere o se rinde)
@personajes_bp.route("/<int:pid>/eliminate", methods=["PATCH"])
@jwt_required()
def eliminar_personaje(pid):
    user_id = get_jwt_identity()
    p = Personaje.query.get_or_404(pid)
    if p.usuario_id != user_id:
        return jsonify({"error":"no autorizado"}), 403
    if p.estado == "eliminado" or p.estado == "spectator":
        return jsonify({"error":"ya eliminado/espectador"}), 400
    p.estado = "spectator"
    db.session.commit()
    # log evento
    evt = GameEvent(partida_id=p.partida_id, personaje_id=p.id, event_type="eliminated", description=f"{p.nombre} quedó eliminado y ahora es espectador")
    db.session.add(evt)
    db.session.commit()
    return jsonify({"message":"personaje marcado como espectador"})

# salir de la partida (left)
@personajes_bp.route("/<int:pid>/leave", methods=["POST"])
@jwt_required()
def salir_partida(pid):
    user_id = get_jwt_identity()
    p = Personaje.query.get_or_404(pid)
    if p.usuario_id != user_id:
        return jsonify({"error":"no autorizado"}), 403
    if p.estado == "activo":
        return jsonify({"error":"un personaje activo no puede salirse"}), 400
    p.estado = "left"
    db.session.commit()
    evt = GameEvent(partida_id=p.partida_id, personaje_id=p.id, event_type="leave", description=f"{p.nombre} abandonó la partida")
    db.session.add(evt)
    db.session.commit()
    return jsonify({"message":"salió de la partida"})
