# Este código pertenece al archivo: dnd_app/routes/chat.py

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..models import GameEvent, Personaje, Partida # Importación relativa
from .. import db

chat_bp = Blueprint("chat", __name__)

@chat_bp.route("/<int:partida_id>", methods=["GET"])
@jwt_required()
def get_chat(partida_id):
    partida = Partida.query.get(partida_id)
    if not partida:
        return jsonify({"msg": "Partida no encontrada"}), 404

    eventos = GameEvent.query.filter_by(partida_id=partida_id).order_by(GameEvent.timestamp.asc()).all()
    
    eventos_json = [{
        "id": evento.id,
        "type": evento.event_type,
        "description": evento.description,
        "timestamp": evento.timestamp.isoformat()
    } for evento in eventos]

    return jsonify(eventos_json), 200

@chat_bp.route("/<int:partida_id>/send", methods=["POST"])
@jwt_required()
def send_message(partida_id):
    usuario_id = get_jwt_identity()
    data = request.get_json()
    mensaje = data.get("mensaje")
    
    personaje = Personaje.query.filter_by(usuario_id=usuario_id, partida_id=partida_id).first()
    
    if not personaje:
        return jsonify({"msg": "No eres un jugador en esta partida"}), 403
    
    if not mensaje:
        return jsonify({"msg": "Mensaje no puede estar vacío"}), 400

    nuevo_evento = GameEvent(
        event_type="chat_message",
        description=f"{personaje.nombre}: {mensaje}",
        partida_id=partida_id,
        personaje_id=personaje.id
    )
    
    db.session.add(nuevo_evento)
    db.session.commit()

    return jsonify({"msg": "Mensaje enviado con éxito", "id": nuevo_evento.id}), 201
