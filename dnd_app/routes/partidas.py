from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from dnd_app import db
from dnd_app.models import Partida, Personaje, GameEvent

partidas_bp = Blueprint("partidas", __name__)

@partidas_bp.route("/create", methods=["POST"])
@jwt_required()
def crear_partida():
    data = request.get_json()
    nombre = data.get("nombre")
    descripcion = data.get("descripcion", "")
    if not nombre:
        return jsonify({"error":"nombre requerido"}), 400
    p = Partida(nombre=nombre, descripcion=descripcion)
    db.session.add(p)
    db.session.commit()
    return jsonify({"message":"Partida creada","id":p.id}), 201

@partidas_bp.route("/<int:pid>", methods=["GET"])
@jwt_required()
def detalle_partida(pid):
    user_id = get_jwt_identity()
    partida = Partida.query.get_or_404(pid)
    # verificar si el usuario tiene o tuvo un personaje en la partida
    acceso = Personaje.query.filter_by(usuario_id=user_id, partida_id=pid).first()
    if not acceso:
        return jsonify({"error":"no tienes acceso a esta partida"}), 403
    personajes = Personaje.query.filter_by(partida_id=pid).all()
    out = []
    for p in personajes:
        out.append({"id":p.id,"nombre":p.nombre,"nivel":p.nivel,"estado":p.estado})
    return jsonify({"id":partida.id,"nombre":partida.nombre,"personajes":out})
