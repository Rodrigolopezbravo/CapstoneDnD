import oracledb
import os

os.environ["TNS_ADMIN"] = r"C:\instantclient_23_9\network\admin"

# ==============================================================================
# 1. CONFIGURACIÓN DE RUTAS Y CREDENCIALES
# ==============================================================================
INSTANT_CLIENT_DIR = r"C:\instantclient_23_9"  # Ajustado a tu ruta real
DB_USER = "ADMIN"
DB_PASSWORD = "DnD2025!Enc0unters#"
SERVICE_NAME = "dndcapstonedb_high"

oracledb.init_oracle_client(lib_dir=INSTANT_CLIENT_DIR)


def get_connection_pool():

    try:
        pool = oracledb.create_pool(
            user=DB_USER,
            password=DB_PASSWORD,
            dsn=SERVICE_NAME
        )
        print("✅ Pool de conexiones creado con éxito.")
        return pool
    except oracledb.Error as e:
        error, = e.args
        print("\n❌ FALLO DE CONEXIÓN.")
        print(f"   Código de error de Oracle: {error.code}")
        print(f"   Mensaje de error: {error.message}")
        return None
    except Exception as e:
        print(f"Ocurrió un error inesperado: {e}")
        return None
