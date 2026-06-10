# ...existing code...
import streamlit as st
import pandas as pd
import os

st.set_page_config(page_title="Tasador SII", layout="wide")

@st.cache_data
def load_data(path="sii_base.csv"):
    # detectar la fila del encabezado buscando "Código SII"
    header_row = 0
    if not os.path.exists(path):
        raise FileNotFoundError(f"{path} no existe")
    with open(path, "r", encoding="utf-8-sig") as f:
        for i, line in enumerate(f):
            if "Código SII" in line or "Codigo SII" in line or "Codigo" in line:
                header_row = i
                break

    # leer usando la fila detectada como header
    df = pd.read_csv(path, header=header_row, dtype=str, encoding="utf-8-sig")
    # marcar celdas vacías como NA y eliminar columnas totalmente vacías
    df = df.replace(r'^\s*$', pd.NA, regex=True)
    df = df.dropna(axis=1, how='all')
    # volver a rellenar NA con cadena vacía para evitar problemas en UI
    df = df.fillna("")
    return df

df = load_data()

# --- Estilos y título ---
st.markdown(
    """
    <style>
    .stApp { background-color: #0b0f14; color: #e6eef6; }
    .big-title { font-size:34px; font-weight:700; margin-bottom:8px; color:#ffffff; }
    .subtle { color: #9aa6b2; }
    .stButton>button { background-color: #1f6feb; }
    .metric { background: rgba(255,255,255,0.03); padding:10px; border-radius:8px; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="big-title">🚗 Tasador Vehicular SII</div>', unsafe_allow_html=True)
st.markdown('<div class="subtle">Filtra por Marca, Modelo y Año. Usa los filtros adicionales si los necesitas.</div>', unsafe_allow_html=True)
st.write("")  # espacio

# --- Botón para reiniciar filtros ---
if st.button("Limpiar filtros"):
    for k in list(st.session_state.keys()):
        if k.startswith(("marca","modelo","anio","col_")):
            del st.session_state[k]

# --- Selects en una fila (con checks por cantidad de columnas) ---
ncols = df.shape[1]

c1, c2, c3 = st.columns([1,1,1])
with c1:
    if ncols > 3:
        marca_opts = sorted(df.iloc[:,3].dropna().unique().tolist())
    else:
        marca_opts = []
    marca = st.selectbox("Marca", [""] + marca_opts, key="marca")
with c2:
    modelo_opts = []
    if marca and ncols > 4:
        modelo_opts = sorted(df[df.iloc[:,3]==marca].iloc[:,4].dropna().unique().tolist())
    modelo = st.selectbox("Modelo", [""] + modelo_opts, key="modelo")
with c3:
    anio_opts = []
    if marca and modelo and ncols > 1:
        anio_opts = sorted(df[(df.iloc[:,3]==marca) & (df.iloc[:,4]==modelo)].iloc[:,1].astype(str).dropna().unique().tolist())
    anio = st.selectbox("Año", [""] + anio_opts, key="anio")

# --- Aplicar filtros sobre copia para preservar df original ---
d_filtered = df.copy()
if marca and ncols > 3:
    d_filtered = d_filtered[d_filtered.iloc[:,3]==marca]
if modelo and ncols > 4:
    d_filtered = d_filtered[d_filtered.iloc[:,4]==modelo]
if anio and ncols > 1:
    d_filtered = d_filtered[d_filtered.iloc[:,1].astype(str)==anio]

# --- Filtros adicionales (columnas 9,11,12 si existen) ---
extra_cols = [9,11,12]
valid_extra = [c for c in extra_cols if c < ncols]
if valid_extra:
    cols_ui = st.columns([1]*len(valid_extra))
    for i, col_idx in enumerate(valid_extra):
        vals = sorted([v for v in d_filtered.iloc[:,col_idx].dropna().unique() if v != ""])
        if len(vals) > 0:
            with cols_ui[i]:
                label = df.columns[col_idx] if isinstance(df.columns[col_idx], str) else f"Col {col_idx}"
                sel = st.selectbox(label, ["Todas"] + vals, key=f"col_{col_idx}")
                if sel and sel != "Todas":
                    d_filtered = d_filtered[d_filtered.iloc[:,col_idx] == sel]

# --- Mostrar cantidad de resultados destacado ---
st.markdown(f"<div class='metric'>Resultados encontrados: <strong>{len(d_filtered)}</strong></div>", unsafe_allow_html=True)
st.write("")

# --- Quitar columnas no necesarias (índices 8,13,14,15,17,18) ---
drop_idxs = [i for i in [8,13,14,15,17,18] if i < d_filtered.shape[1]]
if drop_idxs:
    cols_to_drop = d_filtered.columns[drop_idxs].tolist()
    d_display = d_filtered.drop(columns=cols_to_drop)
else:
    cols_to_drop = []
    d_display = d_filtered.copy()

# --- Mantener nombres reales del csv (limpiar espacios) y asegurar unicidad ---
clean_names = []
for c in d_display.columns:
    name = c.strip() if isinstance(c, str) else str(c)
    clean_names.append(name)

# asegurar unicidad añadiendo sufijos sólo si hay duplicados
seen = {}
uniq_names = []
for name in clean_names:
    if name in seen:
        seen[name] += 1
        uniq_names.append(f"{name} ({seen[name]})")
    else:
        seen[name] = 0
        uniq_names.append(name)

d_display.columns = uniq_names

# --- Mostrar la tabla con encabezado claro ---
st.markdown("#### Tabla de resultados")
if d_display.shape[1] == 0:
    st.info("No hay columnas para mostrar (se eliminaron columnas solicitadas). Revisa la lista de índices a eliminar si es necesario.")
else:
    st.dataframe(d_display.reset_index(drop=True), use_container_width=True)
# ...existing code...