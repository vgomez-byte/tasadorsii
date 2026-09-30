import pandas as pd
import requests
import streamlit as st

import sii_matcher as sm
from ficha_maia import (
    CAMPOS, OPCIONES_MAIA, ficha_desde_getapi, normalizar_ficha, parsear_texto_maia,
)
from getapi_service import GetAPIConfigError, consultar_patente

st.set_page_config(page_title="Tasador SII", layout="wide")

st.markdown(
    """
    <style>
    .stApp { background-color: #0b0f14; color: #e6eef6; }
    .big-title { font-size:34px; font-weight:700; margin-bottom:8px; color:#ffffff; }
    .subtle { color: #9aa6b2; }
    .stButton>button { background-color: #1f6feb; color: #ffffff; }
    .valor-card { background: rgba(255,255,255,0.03); border: 1px solid #1f2937;
                  border-radius: 10px; padding: 14px 18px; }
    .valor-label { color:#9aa6b2; font-size:14px; font-weight:600; }
    .valor-num { color:#ffffff; font-size:28px; font-weight:700; }
    .badge { display:inline-block; padding:2px 10px; border-radius:12px; font-weight:600; font-size:13px; }
    .alta { background:#0f5132; color:#d1e7dd; }
    .media { background:#664d03; color:#fff3cd; }
    .baja { background:#842029; color:#f8d7da; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Datos
# ---------------------------------------------------------------------------
@st.cache_resource(show_spinner="Cargando bases SII (solo la primera vez)...")
def cargar_bases():
    return sm.preparar_bases("sii_base.csv", "pes2026.csv")


try:
    BASE = cargar_bases()
except Exception as e:  # archivo faltante o mal formado
    st.error(f"No fue posible cargar las bases SII: {e}")
    st.stop()


def clave(campo):
    return f"f_{campo}"


def cargar_en_formulario(datos: dict, sobrescribir: bool = True):
    """
    Deja los datos en el formulario (antes de dibujar los widgets).
    Con sobrescribir=True se parte de un formulario vacío, para que no queden
    datos del vehículo anterior (por ejemplo, la versión de otra patente).
    """
    if sobrescribir:
        for campo in CAMPOS:
            st.session_state[clave(campo)] = ""
    for campo, valor in datos.items():
        if campo not in CAMPOS:
            continue
        if sobrescribir or not st.session_state.get(clave(campo)):
            st.session_state[clave(campo)] = str(valor)
    st.session_state.pop("resultado", None)


def pesos(n) -> str:
    try:
        return "$" + f"{int(n):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "—"


# Aplicar cargas pendientes (desde patente o texto pegado) antes de crear widgets
if "pendiente" in st.session_state:
    datos, sobrescribir = st.session_state.pop("pendiente")
    cargar_en_formulario(datos, sobrescribir)

st.markdown('<div class="big-title">Tasador Vehicular SII</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="subtle">Busca el Código SII y la Tasación Fiscal usando los datos de la '
    "ficha Detalle de MAIA. Puede partir por la patente (GetAPI), pegar el texto de la "
    "ficha o escribir los datos directamente.</div>",
    unsafe_allow_html=True,
)
st.write("")

# ---------------------------------------------------------------------------
# 1. Fuentes de datos
# ---------------------------------------------------------------------------
tab_patente, tab_pegar = st.tabs(["Consultar patente (GetAPI)", "Pegar ficha Detalle de MAIA"])

with tab_patente:
    c1, c2 = st.columns([3, 1])
    patente = c1.text_input("Patente", placeholder="Ej: SGXR43", key="patente")
    patente = patente.upper().replace("-", "").replace(" ", "").strip()
    solo_vacios = c2.checkbox(
        "Solo completar vacíos", value=False,
        help="Si está marcado, no reemplaza datos que ya estén en el formulario (por ejemplo, los pegados desde MAIA).",
    )
    consultar = st.button("Consultar patente", key="btn_patente")
    if consultar and not patente:
        st.warning("Ingrese una patente.")
    elif consultar:
        try:
            with st.spinner("Consultando GetAPI..."):
                ficha = ficha_desde_getapi(consultar_patente(patente))
            if not ficha:
                st.warning("GetAPI no devolvió datos para esa patente.")
            else:
                st.session_state["pendiente"] = (ficha, not solo_vacios)
                st.session_state["origen"] = f"GetAPI · patente {patente}"
                st.session_state.pop("campos_leidos", None)
                st.rerun()
        except GetAPIConfigError as e:
            st.error(str(e))
        except requests.HTTPError as e:
            codigo = e.response.status_code if e.response is not None else "?"
            st.error(f"GetAPI respondió con error {codigo} para la patente {patente}.")
        except requests.RequestException as e:
            st.error(f"No fue posible conectar con GetAPI: {e}")

with tab_pegar:
    st.caption(
        "En MAIA abra la ficha del vehículo → pestaña Detalle → seleccione el contenido "
        "(Ctrl+A) → copie (Ctrl+C) y péguelo aquí. Se reconocen Marca, Modelo, Año, Versión, "
        "Tipo de Vehículo, Tipo de Combustible, Transmisión, Cilindrada, Tracción, Nº Puertas "
        "y Código Avalúo SII."
    )
    texto = st.text_area("Texto copiado desde MAIA", height=160, key="texto_maia")
    if st.button("Cargar datos de la ficha", key="btn_pegar"):
        datos = normalizar_ficha(parsear_texto_maia(texto))
        if not datos:
            st.warning("No se reconoció ningún campo. Revise que el texto incluya las etiquetas de la ficha.")
        else:
            st.session_state["pendiente"] = (datos, True)
            st.session_state["origen"] = "Ficha MAIA (texto pegado)"
            st.session_state["campos_leidos"] = sorted(CAMPOS[c][0] for c in datos)
            st.rerun()
    if st.session_state.get("campos_leidos"):
        st.success("Campos leídos: " + ", ".join(st.session_state["campos_leidos"]))

# ---------------------------------------------------------------------------
# 2. Formulario: mismos campos que la ficha Detalle de MAIA
# ---------------------------------------------------------------------------
st.markdown("### Datos del vehículo (ficha Detalle MAIA)")
if st.session_state.get("origen"):
    st.caption(f"Datos cargados desde: {st.session_state['origen']}. Puede corregirlos antes de buscar.")


def selector(col, campo):
    label = CAMPOS[campo][0]
    opciones = [""] + OPCIONES_MAIA[campo]
    actual = st.session_state.get(clave(campo), "")
    if actual and actual not in opciones:
        opciones.append(actual)        # valor que no está en MAIA: se conserva igual
    if clave(campo) not in st.session_state:
        st.session_state[clave(campo)] = ""
    col.selectbox(label, opciones, key=clave(campo))


with st.form("ficha"):
    a1, a2, a3, a4 = st.columns(4)
    a1.text_input("Marca *", key=clave("marca"))
    a2.text_input("Modelo *", key=clave("modelo"))
    a3.text_input("Año *", key=clave("anio"))
    a4.text_input("Versión", key=clave("version"))

    b1, b2, b3, b4 = st.columns(4)
    selector(b1, "tipo")
    selector(b2, "combustible")
    selector(b3, "transmision")
    b4.text_input("Cilindrada", key=clave("cilindrada"), help="Ej: 1600, 1.6 o 1.6L")

    c1, c2, c3, _ = st.columns(4)
    selector(c1, "traccion")
    selector(c2, "puertas")
    c3.text_input("Codigo Avaluo SII (opcional)", key=clave("codigo_sii"),
                  help="Si se conoce (por ejemplo desde GetAPI), se valida contra los demás datos.")

    f1, f2 = st.columns([1, 5])
    buscar = f1.form_submit_button("Buscar avalúo", type="primary")
    limpiar = f2.form_submit_button("Limpiar")

if limpiar:
    for campo in CAMPOS:
        st.session_state.pop(clave(campo), None)
    for k in ("resultado", "origen", "campos_leidos"):
        st.session_state.pop(k, None)
    st.rerun()

if buscar:
    vehiculo = sm.Vehiculo(**{c: st.session_state.get(clave(c), "") for c in CAMPOS})
    with st.spinner("Buscando en la base SII..."):
        st.session_state["resultado"] = sm.tasar(BASE, vehiculo)

# ---------------------------------------------------------------------------
# 3. Resultado
# ---------------------------------------------------------------------------
res = st.session_state.get("resultado")
if res is not None:
    st.divider()
    st.markdown("### Valores")

    if res.candidatos.empty:
        st.error(res.mensaje)
        for adv in res.advertencias:
            st.warning(adv)
    else:
        cands = res.candidatos
        etiquetas = [
            f"{r['Código SII']} · {r['Modelo']} {r['Versión']} · {r['Transmisión']} · "
            f"{pesos(r['Tasación 2026'])} · {r['Puntaje']:.0f} pts"
            for _, r in cands.iterrows()
        ]
        idx = st.selectbox(
            "Coincidencia seleccionada", range(len(etiquetas)),
            format_func=lambda i: ("★ " if i == 0 else "") + etiquetas[i],
            help="Por defecto se muestra la de mayor puntaje. Puede elegir otra si conoce la versión exacta.",
        )
        elegido = cands.iloc[idx]

        conf = res.confianza if idx == 0 else "Manual"
        clase = {"Alta": "alta", "Media": "media", "Baja": "baja"}.get(conf, "media")
        metodo = "Código SII validado" if res.metodo == "codigo_validado" and idx == 0 \
            else "Búsqueda por características"
        st.markdown(
            f'<span class="badge {clase}">Confianza {conf}</span> '
            f'<span class="subtle">&nbsp;{metodo} · puntaje {elegido["Puntaje"]:.0f}/100 · '
            f'base {elegido["Base"]}</span>',
            unsafe_allow_html=True,
        )
        st.write("")

        v1, v2 = st.columns(2)
        with v1:
            st.markdown(
                f'<div class="valor-card"><div class="valor-label">Codigo Avaluo SII</div>'
                f'<div class="valor-num">{elegido["Código SII"]}</div></div>',
                unsafe_allow_html=True,
            )
            st.code(elegido["Código SII"], language=None)
        with v2:
            st.markdown(
                f'<div class="valor-card"><div class="valor-label">Avalúo Fiscal (Tasación 2026)</div>'
                f'<div class="valor-num">{pesos(elegido["Tasación 2026"])}</div></div>',
                unsafe_allow_html=True,
            )
            st.code(str(elegido["Tasación 2026"]), language=None)
        st.caption("Use el botón de copiar de cada recuadro para pegar el valor en MAIA (sección Valores).")

        for adv in res.advertencias:
            st.warning(adv)

        with st.expander("Ver todas las coincidencias y el detalle del puntaje", expanded=conf != "Alta"):
            tabla = cands.copy()
            tabla["Tasación 2026"] = tabla["Tasación 2026"].map(pesos)
            st.dataframe(tabla, width="stretch", hide_index=True)
