import os
import json
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from sqlalchemy import create_engine, text

# Leer JSON desde variable de entorno
sa_info = json.loads(os.environ["GOOGLE_SHEETS_JSON"])
scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
credentials = Credentials.from_service_account_info(sa_info, scopes=scopes)
gc = gspread.authorize(credentials)

# Leer Google Sheet
spreadsheet = gc.open("Trabajo Final NC2025")
hoja = spreadsheet.sheet1
datos = hoja.get_all_records()
df = pd.DataFrame(datos)

# Conectar a PostgreSQL (Railway)
usuario = os.environ["PG_USER"]
contraseña = os.environ["PG_PASSWORD"]
host = os.environ["PG_HOST"]
puerto = os.environ["PG_PORT"]
database = os.environ["PG_DATABASE"]

engine = create_engine(f"postgresql://{usuario}:{contraseña}@{host}:{puerto}/{database}")

# Subir datos a tabla (ajustar nombre si necesario)
df.to_sql('clientes', engine, if_exists='replace', index=False)

with engine.connect() as conn:
    version = conn.execute(text("SELECT version();")).fetchone()
    print("✅ Conectado a PostgreSQL:", version)
