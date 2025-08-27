from werkzeug.security import generate_password_hash, check_password_hash

def hash_password(plain):
    return generate_password_hash(plain)

def check_password(hashed, plain):
    return check_password_hash(hashed, plain)
