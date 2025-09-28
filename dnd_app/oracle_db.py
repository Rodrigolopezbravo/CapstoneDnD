import oracledb
import os
from dnd_app.walletcredentials import INSTANT_CLIENT_DIR, DB_USER, DB_PASSWORD, SERVICE_NAME

os.environ["TNS_ADMIN"] = r"C:\instantclient_23_9\network\admin"


oracledb.init_oracle_client(lib_dir=INSTANT_CLIENT_DIR)


def get_connection_pool():

    try:
        pool = oracledb.create_pool(
            user=DB_USER,
            password=DB_PASSWORD,
            dsn=SERVICE_NAME
        )
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
