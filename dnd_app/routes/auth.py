# dnd_app/routes/auth.py
from flask import Blueprint, request, jsonify, make_response
from flask_jwt_extended import create_access_token, set_access_cookies, unset_jwt_cookies
from dnd_app.utils import hash_password, check_password
import oracledb
import re

# Importar la función de pool de Oracle
from dnd_app.oracle_db import get_connection_pool

auth_bp = Blueprint("auth", __name__)

# Inicializar pool de conexiones Oracle
pool = get_connection_pool()
if not pool:
    raise RuntimeError("No se pudo inicializar el pool de conexiones a Oracle")

# =====================================================================
# Funciones de validación
# =====================================================================
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

def is_valid_email(email):
    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(email_regex, email)

# =========================================================
# Registro de usuario
# =========================================================
@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    username = data.get("username")
    email = data.get("email")
    password = data.get("password")

    # Validaciones iniciales
    if not username or not password or not email:
        return jsonify({"error": "Faltan campos obligatorios"}), 400

    if not is_valid_email(email):
        return jsonify({"error": "Formato de email inválido."}), 400

    password_error = validate_password(password)
    if password_error:
        return jsonify({"error": password_error}), 400

    # Hashear la contraseña en Python
    hashed_password = hash_password(password)

    try:
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                # Llamar procedimiento almacenado en Oracle
                cursor.callproc(
                    "pkg_auth.registrar_usuario",
                    [username, email, hashed_password]
                )
            conn.commit()
    except oracledb.IntegrityError:
        # Manejo de duplicados desde constraint unique
        return jsonify({"error": "El usuario o email ya existe"}), 409
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"message": "Usuario creado con éxito"}), 201


# =========================================================
# Login de usuario
# =========================================================
@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"error": "Faltan credenciales"}), 400

    try:
        with pool.acquire() as conn:
            with conn.cursor() as cursor:
                out_cursor = cursor.var(oracledb.DB_TYPE_CURSOR)
                cursor.callproc("pkg_auth.obtener_usuario", [username, out_cursor])
                row = out_cursor.getvalue().fetchone()
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    if not row or not check_password(row[1], password):
        return jsonify({"error": "Credenciales inválidas"}), 401

    user_id = str(row[0])
    access_token = create_access_token(identity=user_id)
    response = jsonify({"message": "Login exitoso"})
    set_access_cookies(response, access_token)
    return response, 200





@auth_bp.route("/logout", methods=["POST"])
def logout():
    resp = make_response({"msg": "Logout exitoso"})
    # Borrar la cookie
    resp.delete_cookie("access_token_cookie")
    return resp
