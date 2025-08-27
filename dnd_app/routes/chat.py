from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from dnd_app import db
from dnd_app.models import GameMessage, Personaje, Partida

chat_bp = Blueprint("chat", __name__)

@chat_bp.route("/<int:partida_id>/send", methods=["POST"])
@jwt_required()
def send_message(partida_id):
    user_id = get_jwt_identity()
    data = request.get_json()
    content = data.get("content")
    # verificar que el usuario tenga o haya tenido un personaje en la partida
    acceso = Personaje.query.filter_by(usuario_id=user_id, partida_id=partida_id).first()
    if not acceso:
        return jsonify({"error":"no tienes acceso a esta partida"}), 403
    msg = GameMessage(partida_id=partida_id, usuario_id=user_id, content=content)
    db.session.add(msg)
    db.session.commit()
    return jsonify({"message":"enviado","id":msg.id})

@chat_bp.route("/<int:partida_id>/messages", methods=["GET"])
@jwt_required()
def get_messages(partida_id):
    user_id = get_jwt_identity()
    acceso = Personaje.query.filter_by(usuario_id=user_id, partida_id=partida_id).first()
    if not acceso:
        return jsonify({"error":"no tienes acceso a esta partida"}), 403
    msgs = GameMessage.query.filter_by(partida_id=partida_id).order_by(GameMessage.created_at.asc()).all()
    out = [{"id":m.id,"user_id":m.usuario_id,"content":m.content,"created_at":m.created_at.isoformat()} for m in msgs]
    return jsonify(out)
