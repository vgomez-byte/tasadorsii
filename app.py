import streamlit as st
import pandas as pd
import os
from getapi_service import consultar_patente
import re

def calcular_puntaje(api, fila):
    puntaje = 0
    marca_api = normalizar_texto(api["marca"])
    modelo_api = normalizar_texto(api["modelo"])
    version_api = normalizar_texto(api["version"])
    marca_sii = normalizar_texto(fila.iloc[3])
    modelo_sii = normalizar_texto(fila.iloc[4])
    version_sii = normalizar_texto(fila.iloc[5])

    if marca_api and marca_api != "NO INFORMADA":
        if marca_api == marca_sii:
            puntaje += 20
    modelo_match = False
    # Coincidencia directa
    if modelo_api and modelo_sii:
        if modelo_api == modelo_sii:
            puntaje += 50
            modelo_match = True
        # Ejemplo H7L (API) vs H7 (SII)
        elif modelo_api in modelo_sii or modelo_sii in modelo_api:
            puntaje += 45
            modelo_match = True
        else:
            palabras_api = [
                p for p in modelo_api.split()
                if len(p) > 1
            ]
            palabras_sii = [
                p for p in modelo_sii.split()
                if len(p) > 1
            ]
            coincidencias = 0
            for palabra_api in palabras_api:
                for palabra_sii in palabras_sii:
                    if palabra_api == palabra_sii:
                        coincidencias += 1
                        break
                    # H7L vs H7
                    if (
                        len(palabra_api) >= 2
                        and len(palabra_sii) >= 2
                        and (
                            palabra_api.startswith(palabra_sii)
                            or palabra_sii.startswith(palabra_api)
                        )
                    ):
                        coincidencias += 1
                        break
                    # S PRESSO vs SPRESSO
                    api_sin_espacios = modelo_api.replace(" ", "")
                    sii_sin_espacios = modelo_sii.replace(" ", "")
                    if (
                        api_sin_espacios
                        and sii_sin_espacios
                        and (
                            api_sin_espacios == sii_sin_espacios
                            or api_sin_espacios in sii_sin_espacios
                            or sii_sin_espacios in api_sin_espacios
                        )
                    ):
                        coincidencias += 1
                        break
            if coincidencias >= 2:
                puntaje += 45
                modelo_match = True
            elif coincidencias == 1:
                puntaje += 25
                modelo_match = True

        palabras_version_api = [
            p for p in version_api.split()
            if len(p) > 1
        ]
        palabras_version_sii = [
            p for p in version_sii.split()
            if len(p) > 1
        ]
        coincidencias_version = 0
        for palabra in palabras_version_api:
            if palabra in palabras_version_sii:
                coincidencias_version += 1
        if coincidencias_version >= 2:
            puntaje += 20
        elif coincidencias_version == 1:
            puntaje += 10
        transmision_api = normalizar_texto(api["transmision"])
        transmision_sii = normalizar_texto(fila.iloc[10])
        if transmision_api:
            if transmision_api == transmision_sii:
                puntaje += 20
        combustible_api = normalizar_texto(api["combustible"])
        combustible_sii = normalizar_texto(fila.iloc[9])
        if combustible_api:
            if combustible_api == combustible_sii:
                puntaje += 10
        if api["cc"]:
            cc_api = (
                str(api["cc"])
                .replace(".", "")
                .replace(",", "")
            )
            cc_sii = (
                str(fila.iloc[7])
                .replace(".", "")
                .replace(",", "")
            )
            if cc_api == cc_sii:
                puntaje += 15
        if version_api:
            traccion_sii = normalizar_texto(
                fila.iloc[12]
            )
            if "4X4" in version_api and "4X4" in traccion_sii:
                puntaje += 15
            elif "4X2" in version_api and "4X2" in traccion_sii:
                puntaje += 15
        return puntaje

def buscar_mejores_coincidencias(api):
    resultado = pd.concat(
        [df, df_pesados],
        ignore_index=True
    )
    # FILTRAR MARCA
    if api["marca"] != "NO INFORMADA":
        resultado = resultado[
            resultado.iloc[:, 3]
            .astype(str)
            .apply(normalizar_texto)
            .apply(
                lambda x:
                    normalizar_texto(api["marca"]) in x
                    or x in normalizar_texto(api["marca"])
            )
        ]
    # FILTRAR AÑO
    if api["anio"]:
        resultado = resultado[
            resultado.iloc[:, 1]
            .astype(str)
            .str.strip()
            == api["anio"]
        ]
    # FILTRAR MODELO
    # No descartamos por versión. Solo buscamos que el modelo base
    # tenga alguna coincidencia razonable.
    if api["modelo"]:
        modelo_api = normalizar_texto(api["modelo"])
        def modelo_coincide(fila):
            modelo_sii = normalizar_texto(fila.iloc[4])
            # Coincidencia directa
            if modelo_api in modelo_sii or modelo_sii in modelo_api:
                return True
            # Comparar palabras del modelo
            palabras_api = modelo_api.split()
            for palabra in palabras_api:
                if len(palabra) <= 1:
                    continue
                # Ejemplo: H7L (API) vs H7 (SII)
                if palabra in modelo_sii:
                    return True
                if any(
                    palabra.startswith(token) or token.startswith(palabra)
                    for token in modelo_sii.split()
                    if len(token) >= 2
                ):
                    return True
            return False
        resultado = resultado[
            resultado.apply(modelo_coincide, axis=1)
        ]
    mejor_misma = None
    score_misma = -1
    mejor_distinta = None
    score_distinta = -1
    for _, fila in resultado.iterrows():
        score = calcular_puntaje(api, fila)
        transmision_sii = normalizar_texto(fila.iloc[10])
        transmision_api = normalizar_texto(api["transmision"])
        if transmision_sii == transmision_api:
            if score > score_misma:
                score_misma = score
                mejor_misma = fila
        else:
            if score > score_distinta:
                score_distinta = score
                mejor_distinta = fila
    return mejor_misma, score_misma, mejor_distinta, score_distinta

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
            api = {
                "marca": marca_api,
                "modelo": modelo_api,
                "anio": anio_api,
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
                    f"Mejor coincidencia"
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
                    f"Otra posible coincidencia"
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
            resultado_codigo = df[
                df.iloc[:, 0]
                .astype(str)
                .str.strip()
                .str.upper()
                == codigo_sii.upper()
            ]
            # Si no existe en livianos, buscar en pesados
            if resultado_codigo.empty:
                resultado_codigo = df_pesados[
                    df_pesados.iloc[:, 0]
                    .astype(str)
                    .str.strip()
                    .str.upper()
                    == codigo_sii.upper()
                ]
            # Filtrar por año
            if not resultado_codigo.empty:
                resultado_codigo = resultado_codigo[
                    resultado_codigo.iloc[:, 1]
                    .astype(str)
                    .str.strip()
                    == anio_api.strip()
                ]
            codigo_sii_valido = False

            if not resultado_codigo.empty:
                # Revisar todas las filas encontradas para ese Código SII
                for _, fila_codigo in resultado_codigo.iterrows():
                    modelo_api_normalizado = normalizar_texto(modelo_api)
                    marca_sii_normalizada = normalizar_texto(
                        fila_codigo.iloc[3]
                    )
                    modelo_sii_normalizado = normalizar_texto(
                        fila_codigo.iloc[4]
                    )
                    version_sii_normalizada = normalizar_texto(
                        fila_codigo.iloc[5]
                    )
                    texto_sii = (
                        f"{marca_sii_normalizada} "
                        f"{modelo_sii_normalizado} "
                        f"{version_sii_normalizada}"
                    )
                    transmision_api_normalizada = normalizar_texto(
                        transmision_api
                    )
                    transmision_sii_normalizada = normalizar_texto(
                        fila_codigo.iloc[10]
                    )
                    combustible_api_normalizado = normalizar_texto(
                        combustible_api
                    )
                    combustible_sii_normalizado = normalizar_texto(
                        fila_codigo.iloc[9]
                    )
                    # Modelo
                    palabras_modelo = modelo_api_normalizado.split()
                    modelo_ok = all(
                        palabra in texto_sii
                        for palabra in palabras_modelo
                        if len(palabra) > 1
                    )
                    # Transmisión
                    transmision_ok = (
                        not transmision_api_normalizada
                        or transmision_api_normalizada
                        == transmision_sii_normalizada
                    )
                    # Combustible
                    combustible_ok = (
                        not combustible_api_normalizado
                        or combustible_api_normalizado
                        == combustible_sii_normalizado
                    )
                    if modelo_ok and transmision_ok and combustible_ok:
                        codigo_sii_valido = True
                        break
            if codigo_sii_valido:
                resultado_api = resultado_codigo.copy()
                st.success("Tasación encontrada.")
                if "Tasación 2026" in resultado_api.columns:
                    cols = resultado_api.columns.tolist()
                    cols.remove("Tasación 2026")
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
                    "El Código SII entregado no coincide con "
                    "las características del vehículo. "
                    "Realizando búsqueda por características..."
                )
                api = {
                    "marca": marca_api,
                    "modelo": modelo_api,
                    "anio": anio_api,
                    "version": version_api,
                    "transmision": transmision_api,
                    "combustible": combustible_api,
                    "cc": cc_api
                }
                (
                    mejor_misma,
                    score_misma,
                    mejor_distinta,
                    score_distinta
                ) = buscar_mejores_coincidencias(api)
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
                        f"Otra posible coincidencia "
                        f"({score_distinta} puntos)"
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
                        "No se encontró ninguna coincidencia "
                        "confiable en la base SII."
                    )    
    except Exception as e:
        st.error(f"Error consultando GetAPI: {e}")
st.divider()
