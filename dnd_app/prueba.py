from oracle_db import get_connection_pool


pool = get_connection_pool()

if pool:
    with pool.acquire() as connection:
        print("Conexión adquirida del pool.")
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM Usuario")
            result = cursor.fetchone()
            if result:
                print(f"{result}")