from . import db
from datetime import datetime
from sqlalchemy.types import JSON

# Usuario
class Usuario(db.Model):
    __tablename__ = "usuarios"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True)
    password_hash = db.Column(db.String(200), nullable=False)

    personajes = db.relationship("Personaje", back_populates="usuario")

# Partida (GameSession)
class Partida(db.Model):
    __tablename__ = "partidas"
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False)
    descripcion = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    personajes = db.relationship("Personaje", back_populates="partida")
    encuentros = db.relationship("Encuentro", back_populates="partida")
    eventos = db.relationship("GameEvent", back_populates="partida")
    mensajes = db.relationship("GameMessage", back_populates="partida")

# Personaje
class Personaje(db.Model):
    __tablename__ = "personajes"
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False)
    nivel = db.Column(db.Integer, default=1)
    experiencia = db.Column(db.Integer, default=0)

    # vida
    vida_max = db.Column(db.Integer, default=10)
    vida_actual = db.Column(db.Integer, default=10)

    # stats base
    fuerza = db.Column(db.Integer, default=10)
    destreza = db.Column(db.Integer, default=10)
    constitucion = db.Column(db.Integer, default=10)
    inteligencia = db.Column(db.Integer, default=10)
    sabiduria = db.Column(db.Integer, default=10)
    carisma = db.Column(db.Integer, default=10)
    agilidad = db.Column(db.Integer, default=10)

    # estado
    estado = db.Column(db.String(20), default="activo")  # active, eliminated, spectator, left
    role = db.Column(db.String(20), default="PLAYER")    # PLAYER / DM

    # relaciones
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    partida_id = db.Column(db.Integer, db.ForeignKey("partidas.id"), nullable=True)

    usuario = db.relationship("Usuario", back_populates="personajes")
    partida = db.relationship("Partida", back_populates="personajes")

    # equipo: guardamos como JSON con ids de items (simple) o como objetos reales
    equipo = db.Column(JSON, default={})  # ejemplo: {"casco": item_id, "armadura": item_id, ...}

    def mod(self, stat_value):
        # modificador estilo D&D
        return (stat_value - 10) // 2

# Item / Equipo (sencillo)
class Item(db.Model):
    __tablename__ = "items"
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False)
    slot = db.Column(db.String(50))            # casco, armadura, guante, botas, anillo1, anillo2, amuleto, arma_melee, arma_ranged, offhand
    rarity = db.Column(db.String(50), default="comun")
    material = db.Column(db.String(50), default="")
    peso = db.Column(db.Integer, default=1)
    bonos = db.Column(JSON, default={})       # ejemplo: {"DEF":2, "AGI": -1, "STR": +1}
    restricciones = db.Column(JSON, default=[])  # lista de clases permitidas, [] == todas

# Encuentro
class Encuentro(db.Model):
    __tablename__ = "encuentros"
    id = db.Column(db.Integer, primary_key=True)
    partida_id = db.Column(db.Integer, db.ForeignKey("partidas.id"), nullable=False)
    nombre = db.Column(db.String(200))
    descripcion = db.Column(db.Text)
    difficulty = db.Column(db.Integer, default=1)
    kind = db.Column(db.String(30), default="combate")  # combate, social, exploracion, trampa
    payload = db.Column(JSON, default={})
    estado = db.Column(db.String(20), default="pendiente")  # pendiente, resuelto
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    partida = db.relationship("Partida", back_populates="encuentros")

# Evento (historial)
class GameEvent(db.Model):
    __tablename__ = "game_events"
    id = db.Column(db.Integer, primary_key=True)
    partida_id = db.Column(db.Integer, db.ForeignKey("partidas.id"))
    personaje_id = db.Column(db.Integer, db.ForeignKey("personajes.id"), nullable=True)
    event_type = db.Column(db.String(80))
    description = db.Column(db.Text)
    xp_gain = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    partida = db.relationship("Partida", back_populates="eventos")
    personaje = db.relationship("Personaje")

# Mensajes de chat
class GameMessage(db.Model):
    __tablename__ = "game_messages"
    id = db.Column(db.Integer, primary_key=True)
    partida_id = db.Column(db.Integer, db.ForeignKey("partidas.id"))
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)  # system can be null or 0
    content = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    partida = db.relationship("Partida", back_populates="mensajes")
