import os
import json
import time
import re
import pandas as pd
import gspread
import psycopg2
from google.oauth2.service_account import Credentials
from sqlalchemy import create_engine, text

def normalizar_numero(valor):
    """
    Convierte formatos argentinos como '46.800,00' en float correcto 46800.00
    y corrige valores float mal interpretados (como 46.8).
    """
    if valor is None or valor == '':
        return None

    # Fuerza a string (incluso si vino como float)
    valor_str = str(valor).strip().replace('$', '').replace(' ', '')

    # Si tiene formato argentino con separador de miles
    if re.match(r'^\d{1,3}(\.\d{3})*(,\d+)?$', valor_str):
        valor_str = valor_str.replace('.', '').replace(',', '.')

    # Si tiene coma decimal sin miles
    elif re.match(r'^\d+(,\d+)?$', valor_str):
        valor_str = valor_str.replace(',', '.')

    # Si tiene formato inglés (2,000.00)
    elif re.match(r'^\d{1,3}(,\d{3})*(\.\d+)?$', valor_str):
        valor_str = valor_str.replace(',', '')

    try:
        num = float(valor_str)
        # 🔹 Corrección adicional: si el número parece ser 46.8 pero debería ser 46800
        # (por tener menos de 3 cifras antes del punto y decimales = 1 o 2)
        if num < 100 and '.' in valor_str and len(valor_str.split('.')[0]) <= 2 and len(valor_str.split('.')[-1]) <= 2:
            num *= 1000
        return num
    except ValueError:
        return None

# 🔹 Conexión a PostgreSQL
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

# 🔹 Autenticación Google Sheets
sa_info = json.loads(os.environ["GOOGLE_SHEETS_JSON"])
scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
credentials = Credentials.from_service_account_info(sa_info, scopes=scopes)
gc = gspread.authorize(credentials)

# 🔹 Abre el archivo de Sheets
spreadsheet_name = "Trabajo Final NC2025"
spreadsheet = gc.open(spreadsheet_name)
print(f"📄 Abierto Google Sheet: {spreadsheet_name}")

# 🔹 Carga hoja por hoja
for hoja in spreadsheet.worksheets():
    nombre_hoja = hoja.title.lower().replace(" ", "_")
    print(f"\n📑 Procesando hoja: {nombre_hoja}")

    datos = hoja.get_all_records()
    df = pd.DataFrame(datos)

    if df.empty:
        print(f"⚠️ Hoja '{nombre_hoja}' vacía. Saltando...")
        continue

    # Nombres válidos de columnas
    df.columns = [
        col.strip().lower().replace(" ", "_") if col.strip() != "" else f"col_{i}"
        for i, col in enumerate(df.columns)
    ]

    # Detectar columnas numéricas por nombre
    columnas_numericas = [
        col for col in df.columns
        if any(palabra in col for palabra in ["importe", "costo", "precio", "cantidad", "monto"])
    ]

    for col in columnas_numericas:
        df[col] = df[col].apply(normalizar_numero)

    # Carga en PostgreSQL
    df.to_sql(nombre_hoja, engine, if_exists="replace", index=False)
    print(f"✅ Hoja '{nombre_hoja}' cargada correctamente.")

# 🔹 Verificación final
with engine.connect() as conn:
    version = conn.execute(text("SELECT version();")).fetchone()
    print("🧠 PostgreSQL versión:", version[0])

print("\n🎯 Sincronización completada con éxito.")
