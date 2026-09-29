"""
Campos de la ventana "Detalle" de la ficha de vehículo en MAIA y utilidades para
llevarlos al tasador: opciones de los selectores, lectura de texto copiado desde
MAIA y conversión de los datos de GetAPI al mismo formato.
"""

import re

from sii_matcher import (
    canon_combustible, canon_transmision, canon_traccion, compacto, parse_cilindrada,
)

# Opciones tal como están configuradas en MAIA (ficha vehículo, sección Detalles)
OPCIONES_MAIA = {
    "tipo": ["STATION WAGON", "HATCHBACK", "VAN", "SUV", "CAMIONETA", "MOTO",
             "CAMIÓN", "FURGÓN", "SEDÁN"],
    "combustible": ["GASOLINA", "DIESEL", "GAS", "NO INFORMADO", "DUAL (GLP/GASOLINA)",
                    "ELÉCTRICO", "HÍBRIDO", "DUAL (ELÉCTRICO/GASOLINA)"],
    "transmision": ["MECÁNICA", "AUTOMÁTICA"],
    "traccion": ["4x4", "4x2", "AWD", "FWD", "RWD", "4WD", "6x4", "N/A"],
    "puertas": ["2", "3", "4", "5"],
}

# campo interno -> (etiqueta visible en MAIA, field_key en MAIA)
CAMPOS = {
    "marca": ("Marca", "marca"),
    "modelo": ("Modelo", "modelo"),
    "anio": ("Año", "ano"),
    "version": ("Versión", "version"),
    "tipo": ("Tipo de Vehículo", "tipo_vehiculo"),
    "combustible": ("Tipo de Combustible", "combustible"),
    "transmision": ("Transmisión", "transmision"),
    "cilindrada": ("Cilindrada", "cilindrada"),
    "traccion": ("Tracción", "traccion"),
    "puertas": ("Nº Puertas", "num_puertas"),
    "codigo_sii": ("Codigo Avaluo SII", "codigo_sii"),
}

# Variantes de etiqueta (compactas) que se reconocen al pegar texto
_ETIQUETAS = {}
for _campo, (_label, _key) in CAMPOS.items():
    for _v in (_label, _key):
        _ETIQUETAS[compacto(_v)] = _campo
_ETIQUETAS.update({
    compacto("Año"): "anio", "ANO": "anio", "ANIO": "anio",
    compacto("Combustible"): "combustible",
    compacto("Tipo"): "tipo",
    compacto("Puertas"): "puertas", compacto("N° Puertas"): "puertas",
    compacto("Número de Puertas"): "puertas",
    compacto("Código SII"): "codigo_sii", compacto("Código Avalúo SII"): "codigo_sii",
    compacto("Cilindrada (CC)"): "cilindrada",
})


def _etiqueta(linea: str):
    limpia = re.sub(r"[*ⓘⓘℹ]", "", linea).strip()
    return _ETIQUETAS.get(compacto(limpia))


def parsear_texto_maia(texto: str) -> dict:
    """
    Lee el texto copiado desde la ventana Detalle de MAIA (Ctrl+A / Ctrl+C) y
    devuelve {campo: valor}. Acepta 'Etiqueta: valor', 'Etiqueta<TAB>valor'
    o la etiqueta en una línea y el valor en la siguiente.
    """
    lineas = [l.strip() for l in str(texto or "").splitlines()]
    lineas = [l for l in lineas if l]
    datos = {}
    i = 0
    while i < len(lineas):
        linea = lineas[i]
        campo, valor = None, None
        m = re.match(r"^(.+?)\s*(?::|\t)\s*(.+)$", linea)
        if m and _etiqueta(m.group(1)):
            campo, valor = _etiqueta(m.group(1)), m.group(2).strip()
        elif _etiqueta(linea):
            campo = _etiqueta(linea)
            if i + 1 < len(lineas) and not _etiqueta(lineas[i + 1]):
                valor = lineas[i + 1]
                i += 1
        if campo and valor and campo not in datos:
            valor = re.sub(r"[*ⓘⓘ]", "", valor).strip()
            if compacto(valor) not in {"", "SELECCIONAR", "SELECCIONE", "NOINFORMADO"}:
                datos[campo] = valor
        i += 1
    return datos


# --- Conversión a las opciones de MAIA ------------------------------------
_COMB_A_MAIA = {"BENCINA": "GASOLINA", "DIESEL": "DIESEL",
                "ELECTRICO": "ELÉCTRICO", "HIBRIDO": "HÍBRIDO"}
_TRANS_A_MAIA = {"AUTOMATICA": "AUTOMÁTICA", "MECANICA": "MECÁNICA"}


def a_opcion_maia(campo: str, valor) -> str:
    """Lleva un valor libre (GetAPI, texto pegado) a la opción equivalente de MAIA."""
    if valor is None or str(valor).strip() == "":
        return ""
    v = str(valor).strip()
    opciones = OPCIONES_MAIA.get(campo)
    if not opciones:
        return v
    for op in opciones:                       # coincidencia directa (sin acentos/mayúsculas)
        if compacto(op) == compacto(v):
            return op
    if campo == "combustible":
        return _COMB_A_MAIA.get(canon_combustible(v), v)
    if campo == "transmision":
        return _TRANS_A_MAIA.get(canon_transmision(v), v)
    if campo == "traccion":
        t = canon_traccion(v)
        if "4X4" in t:
            return "4x4"
        if "4X2" in t:
            return "4x2"
        return v
    if campo == "puertas":
        m = re.search(r"\d", v)
        return m.group(0) if m else v
    if campo == "tipo":
        c = compacto(v)
        for op in opciones:
            if compacto(op) in c or c in compacto(op):
                return op
    return v


def normalizar_ficha(datos: dict) -> dict:
    """Aplica a_opcion_maia a todos los campos con selector."""
    salida = dict(datos)
    for campo in OPCIONES_MAIA:
        if campo in salida:
            salida[campo] = a_opcion_maia(campo, salida[campo])
    return salida


def _txt(x) -> str:
    return "" if x is None else str(x).strip()


def ficha_desde_getapi(respuesta: dict) -> dict:
    """Convierte la respuesta de GetAPI (/vehicles/plate) a los campos de la ficha."""
    data = (respuesta or {}).get("data", {}) or {}
    marca = ""
    if isinstance(data.get("brand"), dict):
        marca = _txt(data["brand"].get("name"))
    if not marca and isinstance(data.get("model"), dict):
        marca = _txt((data["model"].get("brand") or {}).get("name"))
    if not marca and isinstance(data.get("brand"), str):
        marca = _txt(data.get("brand"))
    modelo = _txt((data.get("model") or {}).get("name")) if isinstance(data.get("model"), dict) \
        else _txt(data.get("model"))
    cc = parse_cilindrada(data.get("engine"))
    ficha = {
        "marca": marca.upper(),
        "modelo": modelo.upper(),
        "anio": _txt(data.get("year")),
        "version": _txt(data.get("version")).upper(),
        "combustible": _txt(data.get("fuel")),
        "transmision": _txt(data.get("transmission")),
        "cilindrada": str(cc) if cc else _txt(data.get("engine")),
        "puertas": _txt(data.get("doors")),
        "codigo_sii": _txt(data.get("codeSii")),
    }
    ficha = {k: v for k, v in ficha.items() if v and compacto(v) not in {"NOINFORMADA", "NOINFORMADO"}}
    return normalizar_ficha(ficha)
