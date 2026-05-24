import os
import json
import re
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from sqlalchemy import create_engine, text
from sqlalchemy.types import Numeric, Integer, Text

# -------------------------------
# Helpers
# -------------------------------
def es_nulo(valor):
    return valor is None or (isinstance(valor, float) and pd.isna(valor)) or pd.isna(valor)

def normalizar_numero(valor):
    if es_nulo(valor):
        return None

    if isinstance(valor, bool):
        return int(valor)

    if isinstance(valor, int):
        return valor

    if isinstance(valor, float):
        return round(valor, 2)

    s = str(valor).strip().replace("$", "").replace(" ", "")
    if s == "":
        return None

    if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?", s):
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d+(,\d+)", s):
        s = s.replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", s):
        s = s.replace(",", "")
    else:
        s = s.replace(".", "").replace(",", ".")

    try:
        n = float(s)
        return int(n) if n.is_integer() else round(n, 2)
    except ValueError:
        return None

def parse_fecha(valor):
    if es_nulo(valor):
        return pd.NaT

    if isinstance(valor, pd.Timestamp):
        return valor

    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        if valor > 20000:
            return pd.to_datetime("1899-12-30") + pd.to_timedelta(valor, unit="D")
        return pd.NaT

    s = str(valor).strip()
    if s == "":
        return pd.NaT

    formatos = [
        "%d/%m/%Y",
        "%d/%m/%Y %H:%M:%S",
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M:%S",
    ]

    for fmt in formatos:
        try:
            return pd.to_datetime(s, format=fmt)
        except Exception:
            pass

    return pd.to_datetime(s, errors="coerce", dayfirst=True)

def formatear_fecha(valor):
    if pd.isna(valor):
        return None
    dt = pd.to_datetime(valor, errors="coerce", dayfirst=True)
    if pd.isna(dt):
        return None
    return dt.strftime("%d/%m/%Y")

def es_columna_fecha(col):
    claves = ["fecha", "date", "vencimiento", "emision", "emisión"]
    return any(k in col for k in claves)

def es_columna_numerica(col):
    claves = ["importe", "costo", "precio", "monto", "efectivo", "valor", "total", "saldo", "cantidad"]
    return any(k in col for k in claves)

# -------------------------------
# Google Sheets auth
# -------------------------------
sa_info = json.loads(os.environ["GOOGLE_SHEETS_JSON"])
scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
credentials = Credentials.from_service_account_info(sa_info, scopes=scopes)
gc = gspread.authorize(credentials)

# -------------------------------
# PostgreSQL
# -------------------------------
engine = create_engine(
    f"postgresql://{os.environ['PG_USER']}:{os.environ['PG_PASSWORD']}@{os.environ['PG_HOST']}:{os.environ['PG_PORT']}/{os.environ['PG_DATABASE']}"
)

try:
    with engine.connect() as conn:
        print("🚀 PostgreSQL activo. Resultado:", conn.execute(text("SELECT 1")).fetchone()[0])
except Exception as e:
    print("❌ Error al conectar con PostgreSQL:", e)
    raise

# -------------------------------
# Process sheets
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

    columnas_fecha = [c for c in df.columns if es_columna_fecha(c)]
    columnas_numericas = [c for c in df.columns if es_columna_numerica(c) and c not in columnas_fecha]

    for col in columnas_fecha:
        print(f"🔎 Fechas crudas de {col}:", df[col].head(10).tolist())
        df[col] = df[col].apply(parse_fecha).apply(formatear_fecha)
        print(f"✅ Fechas formateadas de {col}:", df[col].head(10).tolist())

    for col in columnas_numericas:
        print(f"🔎 Números crudos de {col}:", df[col].head(10).tolist())
        df[col] = df[col].apply(normalizar_numero)
        print(f"✅ Números normalizados de {col}:", df[col].head(10).tolist())

    dtype_map = {}
    for col in df.columns:
        if col in columnas_fecha:
            dtype_map[col] = Text()
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

    print(f"✅ Hoja '{nombre_hoja}' cargada con {len(df)} filas.")

# -------------------------------
# Final check
# -------------------------------
with engine.connect() as conn:
    version = conn.execute(text("SELECT version();")).fetchone()
    print("🧠 Conectado a PostgreSQL:", version[0])
