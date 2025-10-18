import os
import json
import time
import re
import pandas as pd
import gspread
import psycopg2
from google.oauth2.service_account import Credentials
from sqlalchemy import create_engine, text

# =====================================================
#  Función de normalización numérica segura
# =====================================================
def normalizar_numero(valor):
    """
    Convierte números en formato argentino (1.234,56) a formato anglosajón (1234.56)
    y devuelve valores float o None si no son numéricos.
    """
    if isinstance(valor, str):
        # Quita espacios y símbolos de moneda
        valor = valor.strip().replace('$', '').replace(' ', '')
        # Elimina puntos de miles y cambia coma por punto decimal
        valor = re.sub(r'\.(?=\d{3}(,|$))', '', valor)  # elimina puntos de miles (ej. 1.234 -> 1234)
        valor = valor.replace(',', '.')  # cambia coma decimal a punto
        try:
            return float(valor)
        except ValueError:
            return None
    return valor


# =====================================================
# Conexión con PostgreSQL (con reintento automático)
# =====================================================
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


# =====================================================
# Autenticación con Google Sheets
# =====================================================
sa_info = json.loads(os.environ["GOOGLE_SHEETS_JSON"])
scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
credentials = Credentials.from_service_account_info(sa_info, scopes=scopes)
gc = gspread.authorize(credentials)


# =====================================================
# 🔹 Apertura del archivo de Sheets
# =====================================================
spreadsheet_name = "Trabajo Final NC2025"
spreadsheet = gc.open(spreadsheet_name)
print(f"📄 Conectado correctamente al archivo: {spreadsheet_name}")


# =====================================================
# Carga de cada hoja en PostgreSQL
# =====================================================
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

    # Normaliza todas las columnas numéricas (decimales, miles, negativos, etc.)
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].apply(normalizar_numero)

    # Sube la hoja a PostgreSQL
    df.to_sql(nombre_hoja, engine, if_exists="replace", index=False)
    print(f"✅ Hoja '{nombre_hoja}' cargada correctamente en PostgreSQL.")


# =====================================================
# 🔹 Verificación final
# =====================================================
with engine.connect() as conn:
    version = conn.execute(text("SELECT version();")).fetchone()
    print("🧠 PostgreSQL versión:", version[0])

print("🎯 Sincronización completada con éxito.")
