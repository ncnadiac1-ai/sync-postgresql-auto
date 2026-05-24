import os
import json
import re
import math
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from sqlalchemy import create_engine, text
from sqlalchemy.types import Numeric, Integer, DateTime, Text

# -------------------------------
# Normalización de números
# -------------------------------
def normalizar_numero(valor):
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None

    if isinstance(valor, bool):
        return int(valor)

    if isinstance(valor, (int,)):
        return int(valor)

    if isinstance(valor, float):
        if float(valor).is_integer():
            return int(valor)
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
    else:
        s = s.replace(".", "").replace(",", ".")

    try:
        n = float(s)
        if n.is_integer():
            return int(n)
        return n
    except ValueError:
        return None

# -------------------------------
# Convertir serial de Google Sheets a datetime
# -------------------------------
def serial_a_datetime(valor):
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return pd.NaT

    if isinstance(valor, pd.Timestamp):
        return valor

    if isinstance(valor, str):
        dt = pd.to_datetime(valor, errors="coerce", dayfirst=True)
        if pd.notna(dt):
            return dt
        try:
            valor = float(valor.replace(",", "."))
        except ValueError:
            return pd.NaT

    if isinstance(valor, (int, float)):
        # Google Sheets / Excel serial date
        # base: 1899-12-30
        if valor > 20000:
            return pd.to_datetime("1899-12-30") + pd.to_timedelta(valor, unit="D")
        return pd.to_datetime(valor, errors="coerce", dayfirst=True)

    return pd.NaT

# -------------------------------
# Identificar si una columna parece fecha/hora
# -------------------------------
def es_columna_fecha(col):
    palabras = ["fecha", "date", "hora", "time", "vencimiento", "emision", "emisión"]
    return any(p in col for p in palabras)

# -------------------------------
# Identificar si una columna es numérica
# -------------------------------
def es_columna_numerica(col):
    palabras = ["importe", "costo", "precio", "monto", "efectivo", "valor", "total", "saldo", "cantidad", "precio_unitario"]
    return any(p in col for p in palabras)

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

    datos = hoja.get_all_records(value_render_option="UNFORMATTED_VALUE")
    df = pd.DataFrame(datos)

    if df.empty:
        print(f"⚠️ Hoja '{nombre_hoja}' vacía. Saltando...")
        continue

    df.columns = [
        col.strip().lower().replace(" ", "_") if str(col).strip() != "" else f"col_{i}"
        for i, col in enumerate(df.columns)
    ]

    columnas_numericas = [col for col in df.columns if es_columna_numerica(col)]
    columnas_fecha = [col for col in df.columns if es_columna_fecha(col)]

    # Primero fechas/horas
    for col in columnas_fecha:
        print(f"🔎 Valores crudos de {col}:", df[col].head(10).tolist())
        df[col] = df[col].apply(serial_a_datetime)
        print(f"✅ Valores convertidos de {col}:", df[col].head(10).tolist())

    # Luego numéricos
    for col in columnas_numericas:
        if col in columnas_fecha:
            continue
        print(f"🔎 Valores crudos de {col}:", df[col].head(10).tolist())
        df[col] = df[col].apply(normalizar_numero)
        print(f"✅ Valores normalizados de {col}:", df[col].head(10).tolist())

    # Tipos para PostgreSQL
    dtype_map = {}
    for col in df.columns:
        if col in columnas_fecha:
            dtype_map[col] = DateTime()
        elif col in columnas_numericas:
            if "cantidad" in col:
                dtype_map[col] = Integer()
            else:
                dtype_map[col] = Numeric(18, 2)
        else:
            dtype_map[col] = Text()

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
