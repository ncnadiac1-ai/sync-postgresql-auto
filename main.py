import os
import json
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from sqlalchemy import create_engine, text

# Autenticación con Google Sheets
sa_info = json.loads(os.environ["GOOGLE_SHEETS_JSON"])
scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
credentials = Credentials.from_service_account_info(sa_info, scopes=scopes)
gc = gspread.authorize(credentials)

# AbrE el archivo de Sheets
spreadsheet = gc.open("Trabajo Final NC2025")

# Conecta a PostgreSQL
engine = create_engine(
    f"postgresql://{os.environ['PG_USER']}:{os.environ['PG_PASSWORD']}@{os.environ['PG_HOST']}:{os.environ['PG_PORT']}/{os.environ['PG_DATABASE']}"
)

# Recorre todas las hojas del archivo
for hoja in spreadsheet.worksheets():
    nombre_hoja = hoja.title.lower().replace(" ", "_")
    print(f"⏳ Procesando hoja: {nombre_hoja}")

    # Lee los datos
    datos = hoja.get_all_records()
    df = pd.DataFrame(datos)

    if df.empty:
        print(f" Hoja {nombre_hoja} está vacía. Saltando...")
        continue

    # Asegura nombres de columnas válidos
    df.columns = [col if col.strip() != '' else f'col_{i}' for i, col in enumerate(df.columns)]

    # Subi a PostgreSQL
    df.to_sql(nombre_hoja, engine, if_exists="replace", index=False)
    print(f"✅ Hoja {nombre_hoja} cargada correctamente.")

# Verificación final
with engine.connect() as conn:
    version = conn.execute(text("SELECT version();")).fetchone()
    print("✅ Conectado a PostgreSQL:", version)
