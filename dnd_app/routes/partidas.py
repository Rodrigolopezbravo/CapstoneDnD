from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..models import Partida, Personaje # Importación relativa
from .. import db

partidas_bp = Blueprint("partidas", __name__)

@partidas_bp.route("/create", methods=["POST"])
@jwt_required()
def create_partida():
    data = request.get_json()
    dm_id = get_jwt_identity()
    nombre = data.get("nombre")

    if not nombre:
        return jsonify({"msg": "El nombre de la partida es obligatorio"}), 400

    nueva_partida = Partida(nombre=nombre, dm_id=dm_id)
    db.session.add(nueva_partida)
    db.session.commit()

    return jsonify({"msg": "Partida creada con éxito", "id": nueva_partida.id}), 201

@partidas_bp.route("/<int:partida_id>", methods=["GET"])
@jwt_required()
def get_partida(partida_id):
    partida = Partida.query.get(partida_id)

    if not partida:
        return jsonify({"msg": "Partida no encontrada"}), 404

    personajes = [
        {"id": p.id, "nombre": p.nombre, "role": p.role}
        for p in partida.personajes
    ]
    
    return jsonify({
        "id": partida.id,
        "nombre": partida.nombre,
        "estado": partida.estado,
        "dm_id": partida.dm_id,
        "personajes": personajes
    }), 200

@partidas_bp.route("/join/<int:partida_id>", methods=["POST"])
@jwt_required()
def join_partida(partida_id):
    usuario_id = get_jwt_identity()
    data = request.get_json()
    personaje_id = data.get("personaje_id")

    if not personaje_id:
        return jsonify({"msg": "Debes especificar un personaje para unirte"}), 400

    partida = Partida.query.get(partida_id)
    personaje = Personaje.query.filter_by(id=personaje_id, usuario_id=usuario_id).first()

    if not partida:
        return jsonify({"msg": "Partida no encontrada"}), 404
    if not personaje:
        return jsonify({"msg": "Personaje no encontrado o no autorizado"}), 404

    # Asocia el personaje a la partida
    personaje.partida_id = partida.id
    db.session.commit()

    return jsonify({"msg": "Te has unido a la partida con éxito"}), 200

@partidas_bp.route("/leave/<int:partida_id>", methods=["POST"])
@jwt_required()
def leave_partida(partida_id):
    usuario_id = get_jwt_identity()
    data = request.get_json()
    personaje_id = data.get("personaje_id")
    
    if not personaje_id:
        return jsonify({"msg": "Debes especificar un personaje para salir"}), 400

    personaje = Personaje.query.filter_by(id=personaje_id, usuario_id=usuario_id).first()
    
    if not personaje:
        return jsonify({"msg": "Personaje no encontrado o no autorizado"}), 404
        
    personaje.partida_id = None
    db.session.commit()
    return jsonify({"msg": "Has salido de la partida con éxito"}), 200
