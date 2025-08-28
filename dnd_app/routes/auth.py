# dnd_app/routes/auth.py
from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token
from dnd_app import db
from dnd_app.models import Usuario
from dnd_app.utils import hash_password, check_password
import re

auth_bp = Blueprint("auth", __name__)

# Función de validación para contraseñas seguras
def validate_password(password):
 
    if len(password) < 8:
        return "La contraseña debe tener al menos 8 caracteres."
    if not re.search(r"[A-Z]", password):
        return "La contraseña debe contener al menos una letra mayúscula."
    if not re.search(r"[a-z]", password):
        return "La contraseña debe contener al menos una letra minúscula."
    if not re.search(r"\d", password):
        return "La contraseña debe contener al menos un número."
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return "La contraseña debe contener al menos un carácter especial."
    return None

# Función de validación para el email
def is_valid_email(email):
    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(email_regex, email)

@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    username = data.get("username")
    email = data.get("email")
    password = data.get("password")

    if not username or not password or not email:
        return jsonify({"error": "Faltan campos obligatorios"}), 400
    
    if not is_valid_email(email):
        return jsonify({"error": "Formato de email inválido."}), 400

    # Llama a la función de validación de contraseña
    password_error = validate_password(password)
    if password_error:
        return jsonify({"error": password_error}), 400

    if Usuario.query.filter_by(username=username).first():
        return jsonify({"error": "El nombre de usuario ya existe"}), 409
    
    if Usuario.query.filter_by(email=email).first():
        return jsonify({"error": "Este email ya está registrado"}), 409

    user = Usuario(username=username, email=email, password_hash=hash_password(password))
    db.session.add(user)
    db.session.commit()
    
    return jsonify({"message": "Usuario creado con éxito"}), 201

@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"error": "Faltan credenciales"}), 400

    user = Usuario.query.filter_by(username=username).first()

    if not user or not check_password(user.password_hash, password):
        return jsonify({"error": "Credenciales inválidas"}), 401

    access_token = create_access_token(identity=user.id)
    
    return jsonify({
        "access_token": access_token,
        "user_id": user.id,
        "username": user.username
    }), 200