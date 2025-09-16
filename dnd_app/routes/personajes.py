from flask import Blueprint, request, jsonify, render_template
from flask_jwt_extended import jwt_required, get_jwt_identity
from dnd_app import db
from dnd_app.models import Personaje, Usuario, Item, Partida, GameEvent, Clase, Raza

personajes_bp = Blueprint("personajes", __name__)

# --- Página de Personajes ---
@personajes_bp.route("/", methods=["GET"])
@jwt_required()
def personajes_page():
    """
    Renderiza la página de personajes para el usuario autenticado.
    Provee listas de clases y razas para el formulario.
    """
    user_id = get_jwt_identity()
    
    clases = Clase.query.all()
    razas = Raza.query.all()
    
    return render_template(
        "personaje.html",
        clases=clases,
        razas=razas
    )

# --- Crear personaje ---
@personajes_bp.route("/create", methods=["POST"])
@jwt_required()
def crear_personaje():
    user_id = get_jwt_identity()
    data = request.get_json()

    nombre = data.get("nombre")
    clase_id = data.get("clase_id")
    raza_id = data.get("raza_id")

    if not nombre:
        return jsonify({"error": "El nombre del personaje es requerido"}), 400

    stats = {
        "fuerza": data.get("fuerza", 10),
        "destreza": data.get("destreza", 10),
        "constitucion": data.get("constitucion", 10),
        "inteligencia": data.get("inteligencia", 10),
        "sabiduria": data.get("sabiduria", 10),
        "carisma": data.get("carisma", 10),
        "agilidad": data.get("agilidad", 10)
    }

    vida_max = 10 + ((stats["constitucion"] - 10) // 2) * 1

    p = Personaje(
        nombre=nombre,
        usuario_id=user_id,
        clase_id=clase_id,
        raza_id=raza_id,
        vida_max=vida_max,
        vida_actual=vida_max,
        **stats
    )

    db.session.add(p)
    db.session.commit()

    return jsonify({"message": "Personaje creado con éxito", "id": p.id}), 201

# --- Listar personajes del usuario ---
@personajes_bp.route("/my", methods=["GET"])
@jwt_required()
def my_personajes():
    user_id = get_jwt_identity()
    personajes = Personaje.query.filter_by(usuario_id=user_id).all()

    lista_personajes = []
    for p in personajes:
        lista_personajes.append({
            "id": p.id,
            "nombre": p.nombre,
            "nivel": p.nivel,
            "vida_actual": p.vida_actual,
            "vida_max": p.vida_max,
            "clase": p.clase.nombre if p.clase else None,
            "raza": p.raza.nombre if p.raza else None,
            "estado": p.estado,
            "partida_id": p.partida_id
        })
    return jsonify(lista_personajes), 200

# --- Equipar ítem ---
@personajes_bp.route("/<int:pid>/equip", methods=["POST"])
@jwt_required()
def equipar(pid):
    user_id = get_jwt_identity()
    p = Personaje.query.get_or_404(pid)

    if p.usuario_id != user_id:
        return jsonify({"error": "No autorizado"}), 403

    data = request.get_json()
    slot = data.get("slot")
    item_id = data.get("item_id")

    item = Item.query.get(item_id)
    if not item:
        return jsonify({"error": "El ítem no existe"}), 404

    equipo_actual = p.equipo or {}
    equipo_actual[slot] = item.id
    p.equipo = equipo_actual

    db.session.commit()
    return jsonify({"message": f"'{item.nombre}' equipado en {slot}"}), 200

# --- Unir personaje a partida ---
@personajes_bp.route("/<int:pid>/join/<int:partida_id>", methods=["POST"])
@jwt_required()
def join_partida(pid, partida_id):
    user_id = get_jwt_identity()
    p = Personaje.query.get_or_404(pid)

    if p.usuario_id != user_id:
        return jsonify({"error": "No autorizado"}), 403
    if p.partida_id:
        return jsonify({"error": "Ya está en otra partida"}), 400

    partida = Partida.query.get(partida_id)
    if not partida:
        return jsonify({"error": "Partida no existe"}), 404

    p.partida_id = partida_id
    db.session.commit()

    evt = GameEvent(partida_id=partida_id, personaje_id=p.id, event_type="join",
                    description=f"{p.nombre} se unió a la partida.")
    db.session.add(evt)
    db.session.commit()

    return jsonify({"message": "Personaje unido a la partida"}), 200

# --- Marcar personaje como espectador/eliminado ---
@personajes_bp.route("/<int:pid>/eliminate", methods=["PATCH"])
@jwt_required()
def eliminar_personaje(pid):
    user_id = get_jwt_identity()
    p = Personaje.query.get_or_404(pid)

    if p.usuario_id != user_id:
        return jsonify({"error": "No autorizado"}), 403

    if p.estado in ["eliminado", "spectator"]:
        return jsonify({"error": "Ya está eliminado o es espectador"}), 400

    p.estado = "spectator"
    db.session.commit()

    evt = GameEvent(partida_id=p.partida_id, personaje_id=p.id, event_type="eliminated",
                    description=f"{p.nombre} fue eliminado.")
    db.session.add(evt)
    db.session.commit()

    return jsonify({"message": "Personaje marcado como espectador"}), 200

# --- Salir de la partida ---
@personajes_bp.route("/<int:pid>/leave", methods=["POST"])
@jwt_required()
def salir_partida(pid):
    user_id = get_jwt_identity()
    p = Personaje.query.get_or_404(pid)

    if p.usuario_id != user_id:
        return jsonify({"error": "No autorizado"}), 403

    if not p.partida_id:
        return jsonify({"error": "No está en ninguna partida"}), 400

    p.estado = "left"
    p.partida_id = None
    db.session.commit()

    evt = GameEvent(personaje_id=p.id, event_type="leave",
                    description=f"{p.nombre} abandonó la partida.")
    db.session.add(evt)
    db.session.commit()

    return jsonify({"message": "Personaje salió de la partida"}), 200
