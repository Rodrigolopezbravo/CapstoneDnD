# dnd_app/models.py
from . import db
from datetime import datetime

class Usuario(db.Model):
    __tablename__ = 'usuarios'
    id = db.Column(db.Integer, primary_key=True)
    nombre_usuario = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    contraseña_hash = db.Column(db.String(128), nullable=False)
    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    personajes = db.relationship('Personaje', backref='usuario', lazy='dynamic')
    partidas_dm = db.relationship('Partida', backref='dm', lazy='dynamic')

class Personaje(db.Model):
    __tablename__ = 'personajes'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    nivel = db.Column(db.Integer, default=1)
    experiencia = db.Column(db.Integer, default=0)
    vida_max = db.Column(db.Integer, default=10)
    vida_actual = db.Column(db.Integer, default=10)
    fuerza = db.Column(db.Integer, default=10)
    destreza = db.Column(db.Integer, default=10)
    constitucion = db.Column(db.Integer, default=10)
    inteligencia = db.Column(db.Integer, default=10)
    sabiduria = db.Column(db.Integer, default=10)
    carisma = db.Column(db.Integer, default=10)
    agilidad = db.Column(db.Integer, default=10)
    estado = db.Column(db.String(50), default='activo')
    role = db.Column(db.String(50), default='PLAYER')
    equipo = db.Column(db.JSON, default={})
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    clase_id = db.Column(db.Integer, db.ForeignKey('clases.id'), nullable=True)
    raza_id = db.Column(db.Integer, db.ForeignKey('razas.id'), nullable=True)
    partida_id = db.Column(db.Integer, db.ForeignKey('partidas.id'), nullable=True)
    clase = db.relationship('Clase', backref='personajes', lazy=True)
    raza = db.relationship('Raza', backref='personajes', lazy=True)
    partida = db.relationship('Partida', backref='personajes', lazy=True)

class Clase(db.Model):
    __tablename__ = 'clases'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), unique=True, nullable=False)
    descripcion = db.Column(db.String(500))

class Raza(db.Model):
    __tablename__ = 'razas'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), unique=True, nullable=False)
    descripcion = db.Column(db.String(500))

class Partida(db.Model):
    __tablename__ = 'partidas'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    estado = db.Column(db.String(50), default='activa')
    dm_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'))

class Encuentro(db.Model):
    __tablename__ = 'encuentros'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    estado = db.Column(db.String(50), default='en_curso')
    partida_id = db.Column(db.Integer, db.ForeignKey('partidas.id'))

class Enemigo(db.Model):
    __tablename__ = 'enemigos'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    vida_max = db.Column(db.Integer)          # ⚡ corregido
    vida_actual = db.Column(db.Integer)
    encuentro_id = db.Column(db.Integer, db.ForeignKey('encuentros.id'))

class GameEvent(db.Model):
    __tablename__ = 'game_events'
    id = db.Column(db.Integer, primary_key=True)
    event_type = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(500), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    partida_id = db.Column(db.Integer, db.ForeignKey('partidas.id'), nullable=True)
    personaje_id = db.Column(db.Integer, db.ForeignKey('personajes.id'), nullable=True)

class Item(db.Model):
    __tablename__ = 'items'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.String(500))
    tipo = db.Column(db.String(50))
