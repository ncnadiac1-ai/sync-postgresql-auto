import os
import json
import time
import re
import pandas as pd
import gspread
import psycopg2
from google.oauth2.service_account import Credentials
from sqlalchemy import create_engine, text

# ========================================
# Función para normalizar formato de argentina
# ========================================
def normalizar_numero(valor):
    """
    Convierte valores numéricos o textuales con formato argentino (1.234,56)
    a formato estándar (1234.56). Devuelve float o el valor original.
    """
    if pd.isna(valor):
        return None

    # Si ya es número, lo devolvemos sin cambios
    if isinstance(valor, (int, float)):
        return float(valor)

    # Convierte a string y limpia
    valor = str(valor).strip().replace('$', '').replace(' ', '')

    # Corrige casos con punto de miles y coma decimal
    # Ej: "2.000,00" → "2000.00", "1.234" → "1234"
    if re.match(r'^\d{1,3}(\.\d{3})*(,\d+)?$', valor):
        valor = valor.replace('.', '').replace(',', '.')
    elif re.match(r'^\d{1,3}(,\d{3})*(\.\d+)?$', valor):
        valor = valor.replace(',', '')  # casos anglosajones tipo 1,234.56

    # Último intento de conversión
    try:
        return float(valor)
    except ValueError:
        return valor


# ========================================
# Conexión a PostgreSQL
# ========================================
PG_URI = (
    f"postgresql://{os.environ['PG_USER']}:{os.environ['PG_PASSWORD']}"
    f"@{os.environ['PG_HOST']}:{os.environ['PG_PORT']}/{os.environ['PG_DATABASE']}"
)

for intento in range(3):
    try:
        engine = create_engine(PG_URI)
        with engine.connect() as conn:
            print(" Conexión exitosa a PostgreSQL.")
            break
    except Exception as e:
        print(f" Error de conexión (intento {intento+1}/3): {e}")
        time.sleep(10)
else:
    raise ConnectionError("No se pudo conectar a PostgreSQL después de 3 intentos.")

# ========================================
# Autenticación Google Sheets
# ========================================
sa_info = json.loads(os.environ["GOOGLE_SHEETS_JSON"])
scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
credentials = Credentials.from_service_account_info(sa_info, scopes=scopes)
gc = gspread.authorize(credentials)

# ========================================
# Abre archivo de Sheets
# ========================================
spreadsheet_name = "Trabajo Final NC2025"
spreadsheet = gc.open(spreadsheet_name)
print(f" Abierto Google Sheet: {spreadsheet_name}")

# ========================================
# Procesa cada hoja
# ========================================
for hoja in spreadsheet.worksheets():
    nombre_hoja = hoja.title.lower().replace(" ", "_")
    print(f" Procesando hoja: {nombre_hoja}")

    datos = hoja.get_all_records()
    df = pd.DataFrame(datos)

    if df.empty:
        print(f" Hoja '{nombre_hoja}' está vacía. Saltando...")
        continue

    # Corrige nombres de columnas
    df.columns = [
        col.strip().lower().replace(" ", "_") if col.strip() != "" else f"col_{i}"
        for i, col in enumerate(df.columns)
    ]

    # Solo aplica normalización a columnas que parecen numéricas
    columnas_numericas = [col for col in df.columns if any(palabra in col for palabra in ["monto", "precio", "importe", "costo", "cantidad"])]
    
    for col in columnas_numericas:
        df[col] = df[col].apply(normalizar_numero)

    # Sube la hoja a PostgreSQL
    df.to_sql(nombre_hoja, engine, if_exists="replace", index=False)
    print(f" Hoja '{nombre_hoja}' cargada correctamente.")

# ========================================
# Verifica conexión final
# ========================================
with engine.connect() as conn:
    version = conn.execute(text("SELECT version();")).fetchone()
    print(" PostgreSQL versión:", version[0])

print(" Sincronización completada con éxito.")
