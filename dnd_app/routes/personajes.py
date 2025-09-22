# dnd_app/routes/personajes.py

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from dnd_app import db
from dnd_app.models import Personaje, Usuario, Item, Partida, GameEvent

personajes_bp = Blueprint("personajes", __name__)

@personajes_bp.route("/create", methods=["POST"])
@jwt_required()
def crear_personaje():
    # Ruta para crear un nuevo personaje para el usuario autenticado
    user_id = get_jwt_identity()
    data = request.get_json()
    nombre = data.get("nombre")
    
    # Valida que el nombre no sea nulo.
    if not nombre:
        return jsonify({"error": "El nombre del personaje es requerido"}), 400
    
    # Define estadísticas por defecto
    stats = {
        "fuerza": data.get("fuerza", 10),
        "destreza": data.get("destreza", 10),
        "constitucion": data.get("constitucion", 10),
        "inteligencia": data.get("inteligencia", 10),
        "sabiduria": data.get("sabiduria", 10),
        "carisma": data.get("carisma", 10),
        "agilidad": data.get("agilidad", 10)
    }

    # Calcula la vida máxima basada en la constitución (estilo D&D).
    vida_max = 10 + ((stats["constitucion"] - 10)//2)*1
    
    # Crea la instancia del personaje con los datos recibidos.
    p = Personaje(nombre=nombre, usuario_id=user_id, vida_max=vida_max, vida_actual=vida_max, **stats)
    
    # Agrega el personaje a la sesión y lo guarda en la base de datos.
    db.session.add(p)
    db.session.commit()
    
    return jsonify({"message": "Personaje creado con éxito", "id": p.id}), 201

@personajes_bp.route("/my", methods=["GET"])
@jwt_required()
def my_personajes():
    # Ruta para obtener todos los personajes del usuario autenticado.
    user_id = get_jwt_identity()
    
    # Busca todos los personajes que pertenecen al usuario.
    personajes = Personaje.query.filter_by(usuario_id=user_id).all()
    
    # Crea una lista de diccionarios para serializar la información.
    lista_personajes = []
    for p in personajes:
        lista_personajes.append({
            "id": p.id,
            "nombre": p.nombre,
            "nivel": p.nivel,
            "vida": p.vida_actual,
            "estado": p.estado,
            "partida_id": p.partida_id
        })
        
    return jsonify(lista_personajes), 200

# equipar (slot simple: casco, armadura, guante, botas, anillo1, anillo2, amuleto, arma_melee, arma_ranged, offhand)
@personajes_bp.route("/<int:pid>/equip", methods=["POST"])
@jwt_required()
def equipar(pid):
    # Ruta para equipar un ítem en un personaje
    user_id = get_jwt_identity()
    p = Personaje.query.get_or_404(pid)
    
    # Valida que el personaje pertenezca al usuario autenticado.
    if p.usuario_id != user_id:
        return jsonify({"error": "No autorizado para equipar este personaje"}), 403
        
    data = request.get_json()
    slot = data.get("slot")
    item_id = data.get("item_id")
    
    # Valida que el ítem exista.
    item = Item.query.get(item_id)
    if not item:
        return jsonify({"error": "El ítem no existe"}), 404
        
    # Lógica para equipar el ítem:
    # 1. Copia el equipo actual.
    # 2. Asigna el ID del ítem al slot.
    # 3. Asigna el nuevo diccionario a `p.equipo` para que SQLAlchemy detecte el cambio.
    equipo_actual = p.equipo or {}
    equipo_actual[slot] = item.id
    p.equipo = equipo_actual
    
    db.session.commit()
    return jsonify({"message": f"'{item.nombre}' equipado en el slot '{slot}'"}), 200

# unir personaje a partida
@personajes_bp.route("/<int:pid>/join/<int:partida_id>", methods=["POST"])
@jwt_required()
def join_partida(pid, partida_id):
    #Ruta para unir un personaje a una partida
    user_id = get_jwt_identity()
    p = Personaje.query.get_or_404(pid)
    
    if p.usuario_id != user_id:
        return jsonify({"error": "No autorizado para unir este personaje"}), 403
        
    if p.partida_id:
        return jsonify({"error": "El personaje ya se encuentra en otra partida"}), 400
        
    partida = Partida.query.get(partida_id)
    if not partida:
        return jsonify({"error": "La partida no existe"}), 404
        
    # Asigna el ID de la partida al personaje.
    p.partida_id = partida_id
    db.session.commit()
    
    # Crea un evento para registrar la unión del personaje.
    evt = GameEvent(partida_id=partida_id, personaje_id=p.id, event_type="join", description=f"{p.nombre} se unió a la partida.")
    db.session.add(evt)
    db.session.commit()
    
    return jsonify({"message": "Personaje unido a la partida exitosamente"}), 200

# eliminar => marcar espectador (cuando muere o se rinde)
@personajes_bp.route("/<int:pid>/eliminate", methods=["PATCH"])
@jwt_required()
def eliminar_personaje(pid):
    # Ruta para marcar un personaje como 'espectador'
    user_id = get_jwt_identity()
    p = Personaje.query.get_or_404(pid)
    
    if p.usuario_id != user_id:
        return jsonify({"error": "No autorizado"}), 403
    
    if p.estado == "eliminado" or p.estado == "spectator":
        return jsonify({"error": "El personaje ya está eliminado o es espectador"}), 400
        
    p.estado = "spectator"
    db.session.commit()
    
    # Log del evento.
    evt = GameEvent(partida_id=p.partida_id, personaje_id=p.id, event_type="eliminated", description=f"{p.nombre} fue eliminado y ahora es espectador.")
    db.session.add(evt)
    db.session.commit()
    
    return jsonify({"message": "Personaje marcado como espectador"}), 200

# salir de la partida (left)
@personajes_bp.route("/<int:pid>/leave", methods=["POST"])
@jwt_required()
def salir_partida(pid):
    # Ruta para que un personaje abandone una partida
    user_id = get_jwt_identity()
    p = Personaje.query.get_or_404(pid)
    
    if p.usuario_id != user_id:
        return jsonify({"error": "No autorizado"}), 403

    # Un personaje puede dejar una partida si está en una
    if not p.partida_id:
        return jsonify({"error": "El personaje no está en ninguna partida"}), 400

    # Marcar el estado como "left" y eliminar la referencia a la partida
    p.estado = "left"
    p.partida_id = None
    db.session.commit()
    
    evt = GameEvent(personaje_id=p.id, event_type="leave", description=f"{p.nombre} abandonó la partida.")
    db.session.add(evt)
    db.session.commit()
    
    return jsonify({"message": "Personaje salió de la partida"}), 200

