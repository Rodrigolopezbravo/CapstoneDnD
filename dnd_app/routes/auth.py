from dnd_app import db
from flask import Blueprint
from dnd_app.models import Usuario
from dnd_app.utils import hash_password, check_password
from flask_jwt_extended import create_access_token

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")
    email = data.get("email")
    if not username or not password:
        return jsonify({"error":"faltan campos"}), 400
    if Usuario.query.filter_by(username=username).first():
        return jsonify({"error":"usuario ya existe"}), 400
    user = Usuario(username=username, email=email, password_hash=hash_password(password))
    db.session.add(user)
    db.session.commit()
    return jsonify({"message":"usuario creado"}), 201

@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")
    if not username or not password:
        return jsonify({"error":"faltan credenciales"}), 400
    user = Usuario.query.filter_by(username=username).first()
    if not user or not check_password(user.password_hash, password):
        return jsonify({"error":"credenciales inválidas"}), 401
    access_token = create_access_token(identity=user.id)
    return jsonify({"token": access_token, "user_id": user.id, "username": user.username})
