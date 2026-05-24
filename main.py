import os
import json
import re
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from sqlalchemy import create_engine, text

# -------------------------------
# 🔹 Función para normalizar números en formato argentino
# -------------------------------
def normalizar_numero(valor):
    if valor is None or valor == '':
        return None
    
    # Si ya es número entero o float, devolverlo directo
    if isinstance(valor, (int, float)):
        return float(valor)
    
    valor_str = str(valor).strip().replace('$', '').replace(' ', '')
    
    # Formato argentino: 310.000,00 → 310000.00
    if re.match(r'^\d{1,3}(\.\d{3})*(,\d+)?$', valor_str):
        valor_str = valor_str.replace('.', '').replace(',', '.')
    # Solo coma decimal: 2000,00 → 2000.00
    elif re.match(r'^\d+(,\d+)?$', valor_str):
        valor_str = valor_str.replace(',', '.')
    # Formato inglés: 2,000.00 → 2000.00
    elif re.match(r'^\d{1,3}(,\d{3})*(\.\d+)?$', valor_str):
        valor_str = valor_str.replace(',', '')
    
    try:
        return float(valor_str)
    except ValueError:
        return None

# -------------------------------
# 🔹 Autenticación Google Sheets
# -------------------------------
sa_info = json.loads(os.environ["GOOGLE_SHEETS_JSON"])
scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
credentials = Credentials.from_service_account_info(sa_info, scopes=scopes)
gc = gspread.authorize(credentials)

# -------------------------------
# 🔹 Conexión a PostgreSQL
# -------------------------------
engine = create_engine(
    f"postgresql://{os.environ['PG_USER']}:{os.environ['PG_PASSWORD']}@{os.environ['PG_HOST']}:{os.environ['PG_PORT']}/{os.environ['PG_DATABASE']}"
)
# 🔍 Test de conexión temprana para despertar Railway
try:
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1")).fetchone()
        print("🚀 Railway PostgreSQL está activo. Resultado:", result[0])
except Exception as e:
    print("❌ Error al conectar con PostgreSQL:", e)

# -------------------------------
# 🔹 Procesamiento de hojas
# -------------------------------
spreadsheet = gc.open("Trabajo Final NC2025")

for hoja in spreadsheet.worksheets():
    nombre_hoja = hoja.title.lower().replace(" ", "_")
    print(f"\n⏳ Procesando hoja: {nombre_hoja}")

    datos = hoja.get_all_records()
    df = pd.DataFrame(datos)

    if df.empty:
        print(f"⚠️ Hoja '{nombre_hoja}' vacía. Saltando...")
        continue

    # Nombres válidos de columnas
    df.columns = [
        col.strip().lower().replace(" ", "_") if col.strip() != '' else f'col_{i}'
        for i, col in enumerate(df.columns)
    ]

    # Detecta columnas numéricas por nombre
    columnas_numericas = [
        col for col in df.columns
        if any(palabra in col for palabra in ["importe", "costo", "precio", "monto", "efectivo", "valor", "total", "saldo"])
    ]

  # Normaliza y convierte a float
    for col in columnas_numericas:
        print(f"Valores crudos de {col}:", df[col].head(10).tolist())
        df[col] = df[col].apply(normalizar_numero)
        print(f"Valores normalizados de {col}:", df[col].head(10).tolist())

    # Carga en PostgreSQL
    df.to_sql(nombre_hoja, engine, if_exists="replace", index=False)
    print(f"✅ Hoja '{nombre_hoja}' cargada correctamente con {len(df)} filas.")

# -------------------------------
# 🔹 Verificación final
# -------------------------------
with engine.connect() as conn:
    version = conn.execute(text("SELECT version();")).fetchone()
    print("🧠 Conectado a PostgreSQL:", version[0])
