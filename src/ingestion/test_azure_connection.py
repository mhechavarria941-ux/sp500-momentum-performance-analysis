import os

from dotenv import load_dotenv
from mssql_python import connect

load_dotenv()

server = os.getenv("AZURE_SQL_SERVER")
database = os.getenv("AZURE_SQL_DATABASE")
username = os.getenv("AZURE_SQL_USERNAME")
password = os.getenv("AZURE_SQL_PASSWORD")

try:
    conn = connect(
        server=server,
        database=database,
        uid=username,
        pwd=password,
        encrypt="yes",
        trust_server_certificate="no"
    )

    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            DB_NAME() AS database_name,
            SUSER_SNAME() AS login_name
    """)

    row = cursor.fetchone()

    print("Connection successful.")
    print(f"Database: {row[0]}")
    print(f"Login: {row[1]}")

    cursor.close()
    conn.close()

except Exception as error:
    print("Connection failed.")
    print(error)