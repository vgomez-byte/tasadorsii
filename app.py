# ...existing code...
import streamlit as st
import pandas as pd
import os
from getapi_service import consultar_patente
import re
from difflib import SequenceMatcher

def similitud(a, b):
    return SequenceMatcher(
        None,
        normalizar_texto(a),
        normalizar_texto(b)
    ).ratio()

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
def normalizar_texto(texto):

    texto = str(texto).upper()

    texto = texto.replace("-", "")
    texto = texto.replace("/", "")
    texto = texto.replace(".", "")
    texto = texto.replace(",", "")

    texto = re.sub(r"\d+\.\d+", "", texto)

    texto = re.sub(r"\s+", " ", texto)

    return texto.strip()
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

# =====================================
# CONSULTA AUTOMÁTICA POR PATENTE
# =====================================

st.markdown("## 🔍 Consulta por Patente")

patente = st.text_input(
    "Ingrese patente",
    placeholder="Ej: SGXR43"
).upper().replace("-", "").strip()

if st.button("Consultar patente", key="btn_patente"):
    try:
        datos = consultar_patente(patente)
        #st.json(datos)  # Mostrar datos crudos para debug
        data = datos.get("data", {})
        codigo_sii = str(data.get("codeSii") or "").strip()
        # Marca
        marca_api = ""
        # Caso 1: brand viene directo en data
        if isinstance(data.get("brand"), dict):
            marca_api = str(
                data.get("brand", {}).get("name") or ""
            ).upper().strip()
    # Caso 2: brand viene dentro del modelo
        if not marca_api:
            marca_api = str(
                (
                    data.get("model", {})
                    .get("brand", {})
                    .get("name")
                ) or ""
            ).upper().strip()
    # Caso 3: si viene como texto
        if not marca_api:
            marca_api = str(data.get("brand") or "").upper().strip()
    # Fallback
        if not marca_api:
            marca_api = "NO INFORMADA"
        modelo_api = str(
            (data.get("model") or {}).get("name") or ""
        ).upper().strip()

        anio_api = str(data.get("year") or "").strip()
        version_api = str(data.get("version") or "").upper().strip()
        combustible_api = str(data.get("fuel") or "").upper().strip()
        transmision_api = str(
            data.get("transmission") or ""
        ).upper().strip()
        cc_api = str(data.get("engine") or "").strip()
        st.success("Vehículo encontrado")

        # Autocompletar filtros manuales
        st.session_state["marca"] = marca_api
        st.session_state["modelo"] = modelo_api
        st.session_state["anio"] = anio_api

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Marca", marca_api)
        with col2:
            st.metric("Modelo", modelo_api)
        with col3:
            st.metric("Año", anio_api)
        col4, col5, col6 = st.columns(3)
        with col4:
            st.metric("Versión", version_api)
        with col5:
            st.metric("Combustible", combustible_api)
        with col6:
            st.metric("Transmisión", transmision_api)

        # =====================================
        # CRUCE AUTOMÁTICO CON SII
        # =====================================
        #st.write("Código SII GetAPI:", codigo_sii)

        #st.write(
        #"Primeros códigos SII del CSV:",
        #df.iloc[:,0].head(10).tolist()
        #)
        # =====================================
        # CRUCE AUTOMÁTICO CON SII
        # =====================================

        st.markdown("### 💰 Tasación SII")

        # DEBUG (puedes borrarlo después)
        st.write("Código SII GetAPI:", codigo_sii)
        
        if not codigo_sii:
            st.warning(
                "GetAPI no entregó Código SII. Buscando por Marca, Modelo y Año..."
            )
                # ===========================
                # Filtrar primero por Marca
                # ===========================

            resultado_api = df.copy()

            if marca_api != "NO INFORMADA":
                resultado_api = resultado_api[
                    resultado_api.iloc[:,3]
                    .astype(str)
                    .apply(normalizar_texto)
                    .apply(
                        lambda x:
                            marca_api in x
                            or x in marca_api
                    )
]
                # ===========================
                # Filtrar por Año
                # ===========================

            if anio_api:
                resultado_api = resultado_api[
                    resultado_api.iloc[:,1]
                    .astype(str)
                    .str.strip()
                    == anio_api
                    ]

                # ===========================
                # Buscar el modelo más parecido
                # ===========================

            mejor_fila = None
            mejor_score = 0

            texto_api = " ".join([
                marca_api,
                modelo_api,
                version_api,
                transmision_api,
                combustible_api,
                cc_api
            ])

            texto_api = normalizar_texto(texto_api)

            for _, fila in resultado_api.iterrows():
                texto_sii = ""
                for i in [3,4,5,9,10,11,12]:
                    if i < len(fila):
                        texto_sii += " " + str(fila.iloc[i])
                texto_sii = normalizar_texto(texto_sii)

                score = similitud(texto_api, texto_sii)
                if score > mejor_score:
                    mejor_score = score
                    mejor_fila = fila.copy()
                    mejor_texto = texto_sii

                
            st.write("Texto GetAPI:", texto_api)
            st.write("Mejor coincidencia:", mejor_texto)
            st.write("Similitud:", round(mejor_score,3))


            if mejor_score >= 0.75:
                st.success("Coincidencia exacta")
                resultado_api = pd.DataFrame([mejor_fila])
            elif mejor_score >= 0.60:
                st.warning(
                    f"Coincidencia aproximada ({mejor_score:.0%})"
                )
                resultado_api = pd.DataFrame([mejor_fila])
            else:
                st.error(
                    "No se encontró una coincidencia confiable."
                )
                resultado_api = pd.DataFrame()
            st.session_state["resultado_patente"] = resultado_api.copy()
            if len(resultado_api) == 0:
                st.error(
                    "No se encontró ninguna coincidencia en la base SII."
                )
            else:
                st.dataframe(
                    resultado_api.reset_index(drop=True),
                    use_container_width=True
                )
        else:
            resultado_api = df[
                df.iloc[:, 0]
                .astype(str)
                .str.strip()
                .str.upper()
                == codigo_sii.upper()
            ]

            # Filtrar además por año
            resultado_api = resultado_api[
                resultado_api.iloc[:, 1]
                .astype(str)
                .str.strip()
                == anio_api.strip()
            ]
            st.write("Después de filtrar por año:")
            st.dataframe(resultado_api)
            st.write("Código buscado:", codigo_sii)
            st.write("Año buscado:", anio_api)
            st.write("Coincidencias por código:")
            st.dataframe(resultado_api)

            if len(resultado_api) == 0:
                st.session_state["resultado_patente"] = resultado_api.copy()    
                st.error(
                    "No se encontró ninguna coincidencia en la base SII."
            )
    except Exception as e:
        st.error(f"Error consultando GetAPI: {e}")
st.divider()
# --- Botón para reiniciar filtros ---
if st.button("Limpiar filtros", key="btn_limpiar"):
    for k in list(st.session_state.keys()):
        if (
            k.startswith(("marca", "modelo", "anio", "col_"))
            or k == "resultado_patente"
        ):
            del st.session_state[k]

# --- Selects en una fila (con checks por cantidad de columnas) ---
