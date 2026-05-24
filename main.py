import os
import json
import re
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from sqlalchemy import create_engine, text
from sqlalchemy.types import Numeric, Integer, DateTime, Text

# -------------------------------
# Función robusta para normalizar números
# -------------------------------
def normalizar_numero(valor):
    if valor is None or pd.isna(valor):
        return None

    if isinstance(valor, (int, float)):
        return float(valor)

    s = str(valor).strip()
    if s == "":
        return None

    s = s.replace("$", "").replace(" ", "")

    # 7.600,00 -> 7600.00
    if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?", s):
        s = s.replace(".", "").replace(",", ".")
    # 7600,00 -> 7600.00
    elif re.fullmatch(r"\d+(,\d+)", s):
        s = s.replace(",", ".")
    # 7,600.00 -> 7600.00
    elif re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", s):
        s = s.replace(",", "")
    # 7600 -> 7600
    else:
        s = s.replace(".", "").replace(",", ".")

    try:
        return float(s)
    except ValueError:
        return None

# -------------------------------
# Autenticación Google Sheets
# -------------------------------
sa_info = json.loads(os.environ["GOOGLE_SHEETS_JSON"])
scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
credentials = Credentials.from_service_account_info(sa_info, scopes=scopes)
gc = gspread.authorize(credentials)

# -------------------------------
# Conexión a PostgreSQL
# -------------------------------
engine = create_engine(
    f"postgresql://{os.environ['PG_USER']}:{os.environ['PG_PASSWORD']}@{os.environ['PG_HOST']}:{os.environ['PG_PORT']}/{os.environ['PG_DATABASE']}"
)

# Test de conexión
try:
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1")).fetchone()
        print("🚀 PostgreSQL activo. Resultado:", result[0])
except Exception as e:
    print("❌ Error al conectar con PostgreSQL:", e)
    raise

# -------------------------------
# Procesamiento de hojas
# -------------------------------
spreadsheet = gc.open("Trabajo Final NC2025")

for hoja in spreadsheet.worksheets():
    nombre_hoja = hoja.title.lower().replace(" ", "_")
    print(f"\n⏳ Procesando hoja: {nombre_hoja}")

    # Mejor que FORMATTED_VALUE para traer el valor real
    datos = hoja.get_all_records(value_render_option="UNFORMATTED_VALUE")
    df = pd.DataFrame(datos)

    if df.empty:
        print(f"⚠️ Hoja '{nombre_hoja}' vacía. Saltando...")
        continue

    # Normalizar nombres de columnas
    df.columns = [
        col.strip().lower().replace(" ", "_") if str(col).strip() != "" else f"col_{i}"
        for i, col in enumerate(df.columns)
    ]

    # Columnas numéricas por nombre
    columnas_numericas = [
        col for col in df.columns
        if any(palabra in col for palabra in [
            "importe", "costo", "precio", "monto", "efectivo", "valor", "total", "saldo", "cantidad"
        ])
    ]

    # Convertir numéricas
    for col in columnas_numericas:
        print(f"🔎 Valores crudos de {col}:", df[col].head(10).tolist())
        df[col] = df[col].apply(normalizar_numero)
        print(f"✅ Valores normalizados de {col}:", df[col].head(10).tolist())

    # Si hay columnas de fecha, intentarlas parsear
    columnas_fecha = [
        col for col in df.columns
        if any(palabra in col for palabra in ["fecha", "date"])
    ]

    for col in columnas_fecha:
        df[col] = pd.to_datetime(df[col], errors="coerce", dayfirst=True)

    # Definir dtypes para PostgreSQL
    dtype_map = {}
    for col in df.columns:
        if col in columnas_numericas:
            if "cantidad" in col:
                dtype_map[col] = Integer()
            else:
                dtype_map[col] = Numeric(18, 2)
        elif col in columnas_fecha:
            dtype_map[col] = DateTime()
        else:
            dtype_map[col] = Text()

    # Cargar en PostgreSQL
    df.to_sql(
        nombre_hoja,
        engine,
        if_exists="replace",
        index=False,
        dtype=dtype_map
    )

    print(f"✅ Hoja '{nombre_hoja}' cargada correctamente con {len(df)} filas.")

# -------------------------------
# Verificación final
# -------------------------------
with engine.connect() as conn:
    version = conn.execute(text("SELECT version();")).fetchone()
    print("🧠 Conectado a PostgreSQL:", version[0])
