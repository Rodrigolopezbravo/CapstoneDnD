import random
from math import floor

# helpers
def tirar_dado(lados=20):
    return random.randint(1, lados)

def modifier(stat):
    return (stat - 10) // 2

# calcula defensa base del defensor teniendo en cuenta AGI y equipo
def calcular_defensa(defensor, item_def_bonus=0):
    agi_mod = modifier(defensor.agilidad)
    return 10 + agi_mod + item_def_bonus

# obtiene bono DEF por la armadura equipada (busca en personaje.equipo y en tabla items si existe)
def suma_def_armadura(personaje, item_lookup):
    # item_lookup: función que dado item_id retorna Item (o None)
    total = 0
    for slot in ["armadura","casco","guante","botas","escudo"]:
        item_id = personaje.equipo.get(slot)
        if item_id:
            it = item_lookup(item_id)
            if it:
                total += it.get("bonos", {}).get("DEF", 0)
    return total

# resolver ataque (melee, ranged, magico)
def resolver_ataque(atacante, defensor, tipo, item_lookup):
    # tipo: "melee","ranged","magico"
    d20 = tirar_dado(20)
    critico = (d20 == 20)
    pifia = (d20 == 1)

    if tipo == "melee":
        mod_atq = modifier(atacante.fuerza)
        daño_dado = tirar_dado(8)
    elif tipo == "ranged":
        mod_atq = modifier(atacante.destreza)
        daño_dado = tirar_dado(6)
    else:  # magico
        mod_atq = modifier(atacante.inteligencia)
        daño_dado = tirar_dado(10)

    tirada_total = d20 + mod_atq
    item_def = suma_def_armadura(defensor, item_lookup)
    defensa = calcular_defensa(defensor, item_def)

    resultado = {
        "atacante_id": atacante.id,
        "defensor_id": defensor.id,
        "tipo": tipo,
        "d20": d20,
        "modificador_usado": mod_atq,
        "tirada_total": tirada_total,
        "defensa": defensa,
        "critico": critico,
        "pifia": pifia,
        "exito": False,
        "dano": 0,
        "hp_defensor": defensor.vida_actual
    }

    # pifia
    if pifia:
        return resultado

    # crítico o daño normal
    if critico or tirada_total >= defensa:
        resultado["exito"] = True
        base_daño = daño_dado + mod_atq
        if base_daño < 1:
            base_daño = 1
        dano = base_daño * (2 if critico else 1)
        defensor.vida_actual -= dano
        resultado["dano"] = dano
        resultado["hp_defensor"] = max(defensor.vida_actual, 0)
        if defensor.vida_actual <= 0:
            defensor.estado = "eliminado"
    return resultado

# huir: devuelve True si huye, False si falla
def intento_huir(personaje, dc=15):
    roll = tirar_dado(20) + modifier(personaje.agilidad)
    return roll >= dc, {"roll_base": roll - modifier(personaje.agilidad), "mod_agilidad": modifier(personaje.agilidad), "total": roll, "dc": dc}

# calcular xp base por tipo y dificultad
XP_RULES = {
    "combate": 50,
    "mision": 200,
    "decision": 100,
    "exploracion": 30
}
def calcular_xp(event_type, difficulty=1):
    base = XP_RULES.get(event_type, 10)
    return base * difficulty
