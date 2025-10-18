import os
import json
import time
import pandas as pd
import gspread
import psycopg2
from google.oauth2.service_account import Credentials
from sqlalchemy import create_engine, text

# ==============================
# 1️⃣ Conexión con PostgreSQL (con reintento automático)
# ==============================
PG_URI = (
    f"postgresql://{os.environ['PG_USER']}:{os.environ['PG_PASSWORD']}"
    f"@{os.environ['PG_HOST']}:{os.environ['PG_PORT']}/{os.environ['PG_DATABASE']}"
)

for intento in range(3):
    try:
        engine = create_engine(PG_URI)
        with engine.connect() as conn:
            print("✅ Conexión exitosa a PostgreSQL.")
            break
    except Exception as e:
        print(f"❌ Error de conexión (intento {intento+1}/3): {e}")
        time.sleep(10)
else:
    raise ConnectionError("No se pudo conectar a PostgreSQL después de 3 intentos.")

# ==============================
# 2️⃣ Autenticación con Google Sheets
# ==============================
sa_info = json.loads(os.environ["GOOGLE_SHEETS_JSON"])
scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
credentials = Credentials.from_service_account_info(sa_info, scopes=scopes)
gc = gspread.authorize(credentials)

# ==============================
# 3️⃣ Apertura del archivo de Sheets
# ==============================
spreadsheet_name = "Trabajo Final NC2025"
spreadsheet = gc.open(spreadsheet_name)
print(f"📄 Conectado correctamente al archivo: {spreadsheet_name}")

# ==============================
# 4️⃣ Carga de cada hoja en PostgreSQL
# ==============================
for hoja in spreadsheet.worksheets():
    nombre_hoja = hoja.title.lower().replace(" ", "_")
    print(f"⏳ Procesando hoja: {nombre_hoja}")

    # Lee los datos
    datos = hoja.get_all_records()
    df = pd.DataFrame(datos)

    if df.empty:
        print(f"⚠️ Hoja '{nombre_hoja}' está vacía. Saltando...")
        continue

    # Asegura nombres válidos de columnas
    df.columns = [
        col.strip().lower().replace(" ", "_") if col.strip() != "" else f"col_{i}"
        for i, col in enumerate(df.columns)
    ]

    # Sube la hoja a PostgreSQL
    df.to_sql(nombre_hoja, engine, if_exists="replace", index=False)
    print(f"✅ Hoja '{nombre_hoja}' cargada correctamente en PostgreSQL.")

# ==============================
# 5️⃣ Verificación final
# ==============================
with engine.connect() as conn:
    version = conn.execute(text("SELECT version();")).fetchone()
    print("🧠 PostgreSQL versión:", version[0])

print("🎯 Sincronización completada con éxito.")

