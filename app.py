import streamlit as st
import pandas as pd
import os
from getapi_service import consultar_patente
import re

def calcular_puntaje(api, fila):
    puntaje = 0

    # MODELO
    modelo_api = normalizar_texto(api["modelo"])
    version_api = normalizar_texto(api["version"])
    texto_api = f"{modelo_api} {version_api}"
    modelo_sii = normalizar_texto(fila.iloc[4])
    version_sii = normalizar_texto(fila.iloc[5])
    texto_sii = f"{modelo_sii} {version_sii}"
    for palabra in texto_api.split():
        if len(palabra) <= 1:
            continue
        if palabra in texto_sii:
            puntaje += 10


    # TRANSMISION
    if api["transmision"]:
        if normalizar_texto(api["transmision"]) == normalizar_texto(fila.iloc[10]):
            puntaje += 20

    # COMBUSTIBLE
    if api["combustible"]:
        if normalizar_texto(api["combustible"]) == normalizar_texto(fila.iloc[9]):
            puntaje += 10

    # CILINDRADA
    if api["cc"]:
        cc_api = api["cc"].replace(".", "").replace(",", "")
        cc_sii = str(fila.iloc[7]).replace(".", "").replace(",", "")
        if cc_api == cc_sii:
            puntaje += 15

    # TRACCION
    if api["version"]:
        if "4X4" in api["version"] and "4X4" in normalizar_texto(fila.iloc[12]):
            puntaje += 15
        if "4X2" in api["version"] and "4X2" in normalizar_texto(fila.iloc[12]):
            puntaje += 15
    return puntaje

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
    reemplazos = {
        "C/": "CARGA ",
        "PLANA": "PLANA ",
        "CPLANA": "CARGA PLANA",
        "C/PLANA": "CARGA PLANA",
        "CHASIS": "",
        "CABINA": "",
        "MECÁNICA": "MECANICA",
        "AUTOMÁTICA": "AUTOMATICA",
        "DC":"DOBLE CABINA",
        "DOBLE CAB": "DOBLE CABINA",
        "C/PLANA": "CARGA PLANA",
        "CARGA PLANA": "CARGA PLANA",
    }
    for viejo, nuevo in reemplazos.items():
        texto = texto.replace(viejo, nuevo)
    texto = (
        texto.replace("Á", "A")
             .replace("É", "E")
             .replace("Í", "I")
             .replace("Ó", "O")
             .replace("Ú", "U")
             .replace("Ü", "U")
    )
    texto = re.sub(r"\bAT\b", "AUTOMATICA", texto)
    texto = re.sub(r"\bMT\b", "MECANICA", texto)
    texto = texto.replace("-", "")
    texto = texto.replace("/", "")
    texto = texto.replace(".", "")
    texto = texto.replace(",", "")
    texto = re.sub(r"\d+\.\d+", "", texto)
    texto = re.sub(r"\b4X2\b", "", texto)
    texto = re.sub(r"\b4X4\b", "", texto)
    texto = re.sub(r"\b2WD\b", "", texto)
    texto = re.sub(r"\b4WD\b", "", texto)
    texto = re.sub(r"\bCC\b", "", texto)
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()

df_pesados = load_data("pes2026.csv")
# Quitar puntos de la tasación
for base in [df, df_pesados]:
    if "Tasación 2026" in base.columns:
        base["Tasación 2026"] = (
            base["Tasación 2026"]
            .astype(str)
            .str.replace(".", "", regex=False)
        )

# Mover Tasación 2026 antes de País
for base in [df, df_pesados]:
    if (
        "Tasación 2026" in base.columns
        and "País" in base.columns
    ):
        columnas = base.columns.tolist()
        columnas.remove("Tasación 2026")
        indice = columnas.index("País")
        columnas.insert(indice, "Tasación 2026")
        base = base[columnas]
        if base is df:
            df = base
        else:
            df_pesados = base       
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

st.markdown('<div class="big-title">Tasador Vehicular SII</div>', unsafe_allow_html=True)

# CONSULTA AUTOMÁTICA POR PATENTE

st.markdown("## Consulta por Patente")

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
        robo_resultado = data.get("rtResult")
        robo_fecha = data.get("rtDate")
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

            #st.markdown("### Estado del vehículo")
            #if robo_resultado:
                #st.error("Vehículo con encargo por robo")
                #if robo_fecha:
                    #st.write("Fecha:", robo_fecha)
            #else:
                #st.success("Sin encargo por robo informado")

        st.markdown("### Tasación SII")
        st.write("Código SII GetAPI:", codigo_sii)
        
        if not codigo_sii:
            resultado_api = pd.concat(
                [df, df_pesados],
                ignore_index=True
            )

            if marca_api != "NO INFORMADA":
                resultado_api = resultado_api[
                    resultado_api.iloc[:,3]
                    .astype(str)
                    .apply(normalizar_texto)
                    .apply(
                        lambda x:
                            marca_api in x
                            or x in marca_api
                    )]  
            if anio_api:
                resultado_api = resultado_api[
                    resultado_api.iloc[:,1]
                    .astype(str)
                    .str.strip()
                    == anio_api
                    ]  
            texto_api = normalizar_texto(
                f"{modelo_api} {version_api}"
            )

            resultado_api = resultado_api[
                (
                    resultado_api.iloc[:,4]
                    .astype(str)
                    .apply(normalizar_texto)
                    + " "
                    + resultado_api.iloc[:,5]
                    .astype(str)
                    .apply(normalizar_texto)
                ).str.contains(
                    texto_api.split()[0],
                    na=False
                )
            ]
            api = {
            "modelo": modelo_api,
            "version": version_api,
            "transmision": transmision_api,
            "combustible": combustible_api,
            "cc": cc_api
            }
            mejor_misma = None
            score_misma = -1
            mejor_distinta = None
            score_distinta = -1
            for _, fila in resultado_api.iterrows():
                score = calcular_puntaje(api, fila)
                transmision_sii = normalizar_texto(fila.iloc[10])
                if transmision_sii == normalizar_texto(transmision_api):
                    if score > score_misma:
                        score_misma = score
                        mejor_misma = fila
                else:
                    if score > score_distinta:
                        score_distinta = score
                        mejor_distinta = fila
            if mejor_misma is not None:
                st.success(
                    f"Mejor coincidencia ({score_misma} puntos)"
                )
                tabla = pd.DataFrame([mejor_misma])

                if "Tasación 2026" in tabla.columns:
                    cols = tabla.columns.tolist()
                    cols.remove("Tasación 2026")

                    if "País" in cols:
                        indice = cols.index("País")
                    else:
                        indice = cols.index("Pais")

                    cols.insert(indice, "Tasación 2026")
                    tabla = tabla[cols]

                st.dataframe(
                    tabla.reset_index(drop=True),
                    use_container_width=True
                )
            if mejor_distinta is not None:
                st.warning(
                    f"Otra posible coincidencia ({score_distinta} puntos)"
                )
                tabla = pd.DataFrame([mejor_distinta])

                if "Tasación 2026" in tabla.columns:
                    cols = tabla.columns.tolist()
                    cols.remove("Tasación 2026")

                    if "País" in cols:
                        indice = cols.index("País")
                    else:
                        indice = cols.index("Pais")

                    cols.insert(indice, "Tasación 2026")
                    tabla = tabla[cols]

                st.dataframe(
                    tabla.reset_index(drop=True),
                    use_container_width=True
                )
            if mejor_misma is None and mejor_distinta is None:
                st.error(
                    "No se encontró ninguna coincidencia en la base SII."
                )           
        else:
            resultado_api = df[
                df.iloc[:, 0]
                .astype(str)
                .str.strip()
                .str.upper()
                == codigo_sii.upper()
            ]

            # Si no existe en livianos, buscar en pesados
            if resultado_api.empty:
                resultado_api = df_pesados[
                    df_pesados.iloc[:,0]
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
            
            if len(resultado_api) == 0:
                st.session_state["resultado_patente"] = resultado_api.copy()    
                st.error(
                    "No se encontró ninguna coincidencia en la base SII."
            )
            elif len(resultado_api) == 1:

                st.success("Tasación encontrada.")
                if "Tasación 2026" in resultado_api.columns:
                    cols = resultado_api.columns.tolist()
                    cols.remove("Tasación 2026")
                    # Insertar Tasación antes de País
                    if "País" in cols:
                        indice = cols.index("País")
                    else:
                        indice = cols.index("Pais")
                    cols.insert(indice, "Tasación 2026")
                    resultado_api = resultado_api[cols]
                st.dataframe(
                    resultado_api.reset_index(drop=True),
                    use_container_width=True
                )

            else:

                st.warning(
                    f"Se encontraron {len(resultado_api)} coincidencias."
                )
                if "Tasación 2026" in resultado_api.columns:
                    cols = resultado_api.columns.tolist()
                    cols.remove("Tasación 2026")
                    # Insertar Tasación antes de País
                    if "País" in cols:
                        indice = cols.index("País")
                    else:
                        indice = cols.index("Pais")
                    cols.insert(indice, "Tasación 2026")
                    resultado_api = resultado_api[cols]
                st.dataframe(
                    resultado_api.reset_index(drop=True),
                    use_container_width=True
                )
    except Exception as e:
        st.error(f"Error consultando GetAPI: {e}")
st.divider()
