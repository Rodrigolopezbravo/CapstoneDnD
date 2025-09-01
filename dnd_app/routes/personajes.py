# dnd_app/routes/personajes.py

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from dnd_app import db
from dnd_app.models import Personaje, Usuario, Partida, GameEvent, Item
from dnd_app.combat import modifier

personajes_bp = Blueprint("personajes", __name__)

@personajes_bp.route("/create", methods=["POST"])
@jwt_required()
def crear_personaje():
    """
    Ruta para crear un nuevo personaje para el usuario autenticado.
    Valida el nombre y las estadísticas proporcionadas por el usuario.
    """
    user_id = get_jwt_identity()
    data = request.get_json()

    nombre = data.get("nombre")
    if not nombre or not isinstance(nombre, str) or len(nombre.strip()) == 0:
        return jsonify({"error": "El nombre del personaje es requerido y debe ser un texto"}), 400
    
    # Define estadísticas predeterminadas y las valida si vienen en el request
    stats = {
        "fuerza": 10,
        "destreza": 10,
        "constitucion": 10,
        "inteligencia": 10,
        "sabiduria": 10,
        "carisma": 10,
        "agilidad": 10
    }
    
    for stat_name in stats.keys():
        value = data.get(stat_name)
        if value is not None:
            try:
                # Asegura que la estadística sea un número entero
                stats[stat_name] = int(value)
            except (ValueError, TypeError):
                return jsonify({"error": f"El valor de '{stat_name}' debe ser un número entero."}), 400

    # Calcula la vida inicial
    vida_max = 10 + (2 * stats["constitucion"]) + (2 * modifier(stats["constitucion"]))

    # Crea el personaje con las estadísticas y vida finales
    nuevo_personaje = Personaje(
        usuario_id=user_id,
        nombre=nombre,
        fuerza=stats["fuerza"],
        destreza=stats["destreza"],
        constitucion=stats["constitucion"],
        inteligencia=stats["inteligencia"],
        sabiduria=stats["sabiduria"],
        carisma=stats["carisma"],
        agilidad=stats["agilidad"],
        vida_actual=vida_max,
        vida_max=vida_max
    )
    
    db.session.add(nuevo_personaje)
    db.session.commit()
    
    return jsonify({
        "message": f"Personaje '{nombre}' creado con éxito.",
        "personaje_id": nuevo_personaje.id
    }), 201

@personajes_bp.route("/<int:pid>", methods=["GET"])
@jwt_required()
def detalle_personaje(pid):
    """
    Ruta para obtener el detalle de un personaje por su ID.
    """
    user_id = get_jwt_identity()
    p = Personaje.query.get_or_404(pid)
    
    if p.usuario_id != user_id:
        return jsonify({"error": "No autorizado"}), 403
        
    return jsonify({
        "id": p.id,
        "nombre": p.nombre,
        "vida_actual": p.vida_actual,
        "vida_max": p.vida_max,
        "estado": p.estado,
        "fuerza": p.fuerza,
        "destreza": p.destreza,
        "constitucion": p.constitucion,
        "inteligencia": p.inteligencia,
        "sabiduria": p.sabiduria,
        "carisma": p.carisma,
        "agilidad": p.agilidad,
        "inventario": p.inventario,
        "equipo": p.equipo,
        "experiencia": p.experiencia,
        "nivel": p.nivel,
        "partida_id": p.partida_id
    }), 200

@personajes_bp.route("/<int:pid>/delete", methods=["DELETE"])
@jwt_required()
def borrar_personaje(pid):
    """
    Ruta para eliminar un personaje.
    """
    user_id = get_jwt_identity()
    p = Personaje.query.get_or_404(pid)
    
    if p.usuario_id != user_id:
        return jsonify({"error": "No autorizado"}), 403

    db.session.delete(p)
    db.session.commit()
    return jsonify({"message": f"Personaje '{p.nombre}' eliminado con éxito"}), 200

@personajes_bp.route("/<int:pid>/join/<int:partida_id>", methods=["POST"])
@jwt_required()
def unirse_partida(pid, partida_id):
    """
    Ruta para que un personaje se una a una partida.
    """
    user_id = get_jwt_identity()
    p = Personaje.query.get_or_404(pid)
    partida = Partida.query.get_or_404(partida_id)
    
    if p.usuario_id != user_id:
        return jsonify({"error": "No autorizado"}), 403
    
    if p.partida_id:
        return jsonify({"error": "El personaje ya está en una partida"}), 400
    
    p.partida_id = partida_id
    db.session.commit()
    
    # Log del evento
    evt = GameEvent(partida_id=partida.id, personaje_id=p.id, event_type="join", description=f"{p.nombre} se unió a la partida.")
    db.session.add(evt)
    db.session.commit()

    return jsonify({"message": "Personaje se unió a la partida"}), 200

@personajes_bp.route("/<int:pid>/leave", methods=["POST"])
@jwt_required()
def salir_partida(pid):
    """
    Ruta para que un personaje abandone una partida.
    """
    user_id = get_jwt_identity()
    p = Personaje.query.get_or_404(pid)
    
    if p.usuario_id != user_id:
        return jsonify({"error": "No autorizado"}), 403

    if not p.partida_id:
        return jsonify({"error": "El personaje no está en ninguna partida"}), 400

    partida_id = p.partida_id
    p.partida_id = None
    db.session.commit()

    # Log del evento
    evt = GameEvent(partida_id=partida_id, personaje_id=p.id, event_type="leave", description=f"{p.nombre} abandonó la partida.")
    db.session.add(evt)
    db.session.commit()

    return jsonify({"message": "Personaje abandonó la partida"}), 200

@personajes_bp.route("/<int:pid>/spectator", methods=["POST"])
@jwt_required()
def ser_espectador(pid):
    """
    Ruta para que un personaje pase a ser espectador.
    Se usa cuando un personaje es eliminado en combate, por ejemplo.
    """
    user_id = get_jwt_identity()
    p = Personaje.query.get_or_404(pid)

    if p.usuario_id != user_id:
        return jsonify({"error": "No autorizado"}), 403
    
    if p.estado == "eliminado" or p.estado == "spectator":
        return jsonify({"error": "El personaje ya está eliminado o es espectador"}), 400
        
    p.estado = "spectator"
    db.session.commit()
    
    # Log del evento
    evt = GameEvent(partida_id=p.partida_id, personaje_id=p.id, event_type="eliminated", description=f"{p.nombre} fue eliminado y ahora es espectador.")
    db.session.add(evt)
    db.session.commit()
    
    return jsonify({"message": "Personaje marcado como espectador"}), 200