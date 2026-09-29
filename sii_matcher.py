"""
Motor de búsqueda de Código SII y Tasación Fiscal.

Reúne en un solo lugar:
  * Carga y limpieza de las bases SII (livianos: sii_base.csv, pesados: pes2026.csv).
  * Normalización de texto y de valores canónicos (combustible, transmisión, tracción...).
  * Validación de un Código SII entregado (p. ej. por GetAPI).
  * Búsqueda por características con puntaje ponderado y nivel de confianza.

No depende de Streamlit, así que se puede probar o reutilizar desde otro script.
"""

from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher

import pandas as pd

# ---------------------------------------------------------------------------
# Columnas estándar (se usan por NOMBRE, nunca por posición)
# ---------------------------------------------------------------------------
COL_CODIGO = "Código SII"
COL_ANIO = "Año"
COL_TIPO = "Tipo"
COL_MARCA = "Marca"
COL_MODELO = "Modelo"
COL_VERSION = "Versión"
COL_PUERTAS = "Puertas"
COL_CC = "Cilindrada (CC)"
COL_COMB = "Combustible"
COL_TRANS = "Transmisión"
COL_TRAC = "Tracción"
COL_TASACION = "Tasación 2026"
COL_BASE = "Base"

COLUMNAS_SALIDA = [
    COL_CODIGO, COL_ANIO, COL_BASE, COL_TIPO, COL_MARCA, COL_MODELO, COL_VERSION,
    COL_PUERTAS, COL_CC, COL_COMB, COL_TRANS, COL_TRAC, COL_TASACION,
]

# Pesos del puntaje (suman 100). Si un dato no viene informado en la ficha
# o no existe en la base, su peso se excluye y el puntaje se re-escala.
PESOS = {
    "marca": 5,
    "modelo": 30,
    "version": 22,
    "transmision": 10,
    "combustible": 8,
    "cilindrada": 12,
    "traccion": 6,
    "puertas": 4,
    "tipo": 3,
}

# Tokens de la versión que en realidad describen transmisión / tracción /
# carrocería. Se sacan de la comparación de versión para no contar doble.
TOKENS_TRANSMISION = {"AT", "MT", "TA", "TM", "AUT", "AUTO", "AUTOMATICA", "AUTOMATICO",
                      "MEC", "MECANICA", "MECANICO", "MANUAL", "CVT", "DCT", "DSG", "TIPTRONIC"}
TOKENS_TRACCION = {"4X4", "4X2", "4WD", "2WD", "AWD", "FWD", "RWD", "6X4", "6X2", "8X4"}
TOKENS_RUIDO = {"CC", "LTS", "LT", "L", "HP", "CV", "P", "PTAS", "PUERTAS", "SIN", "VERSION",
                "C", "S", "A", "E", "DE", "Y", "CON", "NUEVO", "NUEVA", "USADO", "USADA"}


def limpiar_texto_ficha(texto) -> str:
    """Quita comentarios agregados en la ficha: 'CARGO + BATERÍA NUEVA' -> 'CARGO'."""
    t = str(texto or "")
    t = re.split(r"\+|\(", t, maxsplit=1)[0]
    return t.strip()

# Alias de marcas frecuentes (valor ya normalizado y sin espacios -> base SII)
ALIAS_MARCA = {
    "KIA": "KIAMOTORS",
    "VW": "VOLKSWAGEN",
    "MERCEDES": "MERCEDESBENZ",
    "BENZ": "MERCEDESBENZ",
    "CHEVY": "CHEVROLET",
    "GM": "CHEVROLET",
    "LANDROVER": "LANDROVER",
    "HARLEY": "HARLEYDAVIDSON",
    "SYM": "SANYANGSYM",
    "CANAM": "BRPCANAM",
    "GREATWALLMOTORS": "GREATWALL",
    "GWM": "GREATWALL",
    "DS": "DSAUTOMOBILES",
    "DFM": "DONGFENG",
    "DFLM": "DONGFENG",
    "DONGFENGMOTOR": "DONGFENG",
    "DONGFENGMOTORS": "DONGFENG",
}

# Archivo editable por el usuario con más equivalencias (marca_origen,marca_sii)
ARCHIVO_ALIAS_MARCAS = "alias_marcas.csv"


def cargar_alias_marcas(path: str = ARCHIVO_ALIAS_MARCAS) -> dict:
    """Lee alias_marcas.csv (columnas marca_origen, marca_sii) si existe."""
    if not os.path.exists(path):
        return {}
    try:
        df = pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("")
    except Exception:
        return {}
    if not {"marca_origen", "marca_sii"} <= set(df.columns):
        return {}
    return {
        compacto(o): compacto(s)
        for o, s in zip(df["marca_origen"], df["marca_sii"])
        if compacto(o) and compacto(s)
    }


# ---------------------------------------------------------------------------
# Normalización
# ---------------------------------------------------------------------------
def sin_acentos(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", str(texto))
    return "".join(c for c in texto if not unicodedata.combining(c))


def normalizar_texto(texto) -> str:
    """Mayúsculas, sin acentos, puntuación a espacios. Conserva decimales (1.6)."""
    if texto is None or (isinstance(texto, float) and pd.isna(texto)):
        return ""
    t = sin_acentos(str(texto)).upper().strip()
    if t in {"NAN", "NONE", "NO INFORMADA", "NO INFORMADO", "N/A", "S/I", "-"}:
        return ""
    # Abreviaturas de carrocería frecuentes (con límites de palabra)
    t = re.sub(r"\bC/", "CARGA ", t)
    t = re.sub(r"\bDOBLE\s+CAB\b\.?", "DC", t)
    t = re.sub(r"\bDOBLE\s+CABINA\b", "DC", t)
    t = re.sub(r"\bCAB\s+SIMPLE\b|\bCABINA\s+SIMPLE\b", "CS", t)
    t = re.sub(r"\bT/A\b", " AT ", t)
    t = re.sub(r"\bT/M\b", " MT ", t)
    t = re.sub(r"\b(\d{1,2})\s*X\s*(\d{1,2})\b", r"\1X\2", t)      # '4 X 4' -> '4X4'
    # Decimales tipo 1,6 -> 1.6 ; el resto de la puntuación a espacio
    t = re.sub(r"(\d),(\d)", r"\1.\2", t)
    t = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", t)
    t = re.sub(r"[^A-Z0-9.\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def compacto(texto) -> str:
    """Texto normalizado sin espacios ni puntos (para comparar 'S PRESSO' con 'SPRESSO')."""
    return normalizar_texto(texto).replace(" ", "").replace(".", "")


def tokens(texto) -> list[str]:
    """Separa en tokens; '1.6L' -> ['1.6', 'L']."""
    return re.findall(r"\d+\.\d+|[A-Z0-9]+", normalizar_texto(texto))


def tokens_version(texto) -> frozenset:
    return frozenset(
        tk for tk in tokens(texto)
        if tk not in TOKENS_TRANSMISION
        and tk not in TOKENS_TRACCION
        and tk not in TOKENS_RUIDO
        and not re.fullmatch(r"\d+\.\d+", tk)          # la cilindrada se compara aparte
    )


def canon_combustible(valor) -> str:
    t = compacto(valor)
    if not t:
        return ""
    if "DIES" in t or "PETROL" in t:
        return "DIESEL"
    if "HIBR" in t or ("ELECTR" in t and ("GASOL" in t or "BENC" in t)):
        return "HIBRIDO"
    if "ELECTR" in t:
        return "ELECTRICO"
    if "BENC" in t or "GASOL" in t or "NAFTA" in t:
        return "BENCINA"
    if "GLP" in t or "GNC" in t or t == "GAS":
        # La base SII no distingue gas; estos vehículos figuran como bencina.
        return "BENCINA"
    return ""


def canon_transmision(valor) -> str:
    t = compacto(valor)
    if not t:
        return ""
    if t.startswith("AUT") or t in {"AT", "TA", "CVT", "DCT", "DSG"} or "SECUENCIAL" in t:
        return "AUTOMATICA"
    if t.startswith("MEC") or t.startswith("MAN") or t in {"MT", "TM"}:
        return "MECANICA"
    return ""


def canon_traccion(valor) -> frozenset:
    """Devuelve un conjunto: '4x2 y 4x4' -> {'4X2','4X4'}; 'AWD' -> {'4X4'}."""
    t = normalizar_texto(valor)
    if not t:
        return frozenset()
    salida = set()
    for tk in re.findall(r"\d+X\d+|AWD|4WD|2WD|FWD|RWD", t):
        if tk in {"AWD", "4WD"}:
            salida.add("4X4")
        elif tk in {"2WD", "FWD", "RWD"}:
            salida.add("4X2")
        else:
            salida.add(tk)
    return frozenset(salida)


def traccion_desde_texto(*textos) -> frozenset:
    return frozenset().union(*(canon_traccion(t) for t in textos))


def transmision_desde_texto(texto) -> str:
    tks = set(tokens(texto))
    if tks & {"AT", "TA", "AUT", "AUTO", "AUTOMATICA", "AUTOMATICO", "CVT", "DCT", "DSG", "TIPTRONIC"}:
        return "AUTOMATICA"
    if tks & {"MT", "TM", "MEC", "MECANICA", "MECANICO", "MANUAL"}:
        return "MECANICA"
    return ""


def parse_cilindrada(valor) -> int | None:
    """
    '1600' -> 1600 ; '1.6' -> 1600 ; '1,6 L' -> 1600 ; '7.700' (pesados) -> 7700 ; '2.0 TURBO' -> 2000
    """
    if valor is None:
        return None
    t = sin_acentos(str(valor)).upper().strip()
    if not t or t in {"NAN", "NONE"}:
        return None
    m = re.search(r"\d+(?:[.,]\d+)*", t)
    if not m:
        return None
    num = m.group(0)
    partes = re.split(r"[.,]", num)
    try:
        if len(partes) == 1:
            n = int(num)
        elif len(partes) == 2 and len(partes[1]) == 3 and int(partes[0]) >= 1:
            n = int(partes[0] + partes[1])        # separador de miles: 7.700
        else:
            litros = float(partes[0] + "." + "".join(partes[1:]))
            n = int(round(litros * 1000))
    except ValueError:
        return None
    if n < 20:                                      # vino en litros sin decimal ("2")
        n *= 1000
    return n if 40 <= n <= 30000 else None


def parse_entero(valor) -> int | None:
    m = re.search(r"\d+", str(valor or ""))
    return int(m.group(0)) if m else None


def parse_monto(valor) -> int | None:
    t = re.sub(r"[^\d]", "", str(valor or ""))
    return int(t) if t else None


# ---------------------------------------------------------------------------
# Carga de bases
# ---------------------------------------------------------------------------
def _detectar_encabezado(path: str) -> int:
    with open(path, "r", encoding="utf-8-sig") as f:
        for i, linea in enumerate(f):
            if "Código SII" in linea or "Codigo SII" in linea:
                return i
    raise ValueError(f"No se encontró la fila de encabezado 'Código SII' en {path}")


def cargar_base(path: str, nombre_base: str) -> pd.DataFrame:
    if not os.path.exists(path):
        raise FileNotFoundError(f"{path} no existe")
    df = pd.read_csv(path, header=_detectar_encabezado(path), dtype=str, encoding="utf-8-sig")
    df.columns = [str(c).strip() for c in df.columns]
    df = df.rename(columns={"Codigo SII": COL_CODIGO, "Pais": "País"})
    df = df.loc[:, ~df.columns.str.startswith("Unnamed")]
    df = df.fillna("")
    for c in df.columns:
        df[c] = df[c].astype(str).str.strip()
    df = df[df[COL_CODIGO] != ""].copy()
    df[COL_BASE] = nombre_base
    for c in COLUMNAS_SALIDA:
        if c not in df.columns:
            df[c] = ""
    return df


def preparar_bases(path_livianos="sii_base.csv", path_pesados="pes2026.csv") -> pd.DataFrame:
    """Une ambas bases y pre-calcula todas las columnas normalizadas (una sola vez)."""
    partes = [cargar_base(path_livianos, "Livianos")]
    if os.path.exists(path_pesados):
        partes.append(cargar_base(path_pesados, "Pesados"))
    df = pd.concat(partes, ignore_index=True).fillna("")
    ALIAS_MARCA.update(cargar_alias_marcas(
        os.path.join(os.path.dirname(os.path.abspath(path_livianos)), ARCHIVO_ALIAS_MARCAS)))

    df["_tasacion"] = df[COL_TASACION].map(parse_monto)
    df[COL_TASACION] = df["_tasacion"].map(lambda x: "" if x is None else str(x))
    df["_codigo"] = df[COL_CODIGO].str.upper()
    df["_anio"] = df[COL_ANIO].map(parse_entero)
    df["_marca_c"] = df[COL_MARCA].map(compacto)
    df["_modelo_n"] = df[COL_MODELO].map(normalizar_texto)
    df["_modelo_c"] = df[COL_MODELO].map(compacto)
    df["_modelo_t"] = df[COL_MODELO].map(lambda x: frozenset(tokens(x)))
    # Tokens de la versión que no repiten el modelo (ej. 'AEOLUS' / 'Y3 AT CONFORT' -> {Y3, CONFORT})
    df["_version_t"] = [tokens_version(v) - m for v, m in zip(df[COL_VERSION], df["_modelo_t"])]
    df["_version_c"] = df[COL_VERSION].map(compacto)
    df["_comb"] = df[COL_COMB].map(canon_combustible)
    # Transmisión de la columna; si viene vacía (común en pesados), se deduce de la versión ('AT', 'MT')
    df["_trans"] = [canon_transmision(t) or transmision_desde_texto(v)
                    for t, v in zip(df[COL_TRANS], df[COL_VERSION])]
    df["_trac"] = [traccion_desde_texto(a, b) for a, b in zip(df[COL_TRAC], df[COL_VERSION])]
    df["_cc"] = df[COL_CC].map(parse_cilindrada)
    df["_puertas"] = df[COL_PUERTAS].map(parse_entero)
    df["_tipo"] = df[COL_TIPO].map(compacto)
    return df


# ---------------------------------------------------------------------------
# Datos del vehículo a buscar
# ---------------------------------------------------------------------------
# Tipo de vehículo de MAIA -> tipos equivalentes en las bases SII (compactos)
TIPO_MAIA_A_SII = {
    "SEDAN": {"SEDAN"},
    "HATCHBACK": {"HATCHBACK"},
    "STATIONWAGON": {"SUV", "HATCHBACK", "SEDAN"},
    "SUV": {"SUV"},
    "CAMIONETA": {"CAMIONETA"},
    "VAN": {"VAN", "MINIBUS", "COMERCIAL"},
    "FURGON": {"FURGON", "COMERCIAL", "FURGONCARGAGENERAL", "VAN"},
    "MOTO": {"MOTO", "CUATRIMOTO"},
    "CAMION": {"CAMION", "TRACTOCAMION"},
}


@dataclass
class Vehiculo:
    marca: str = ""
    modelo: str = ""
    anio: str = ""
    version: str = ""
    tipo: str = ""
    combustible: str = ""
    transmision: str = ""
    cilindrada: str = ""
    traccion: str = ""
    puertas: str = ""
    codigo_sii: str = ""

    def __post_init__(self):
        self.modelo = limpiar_texto_ficha(self.modelo)
        self.version = limpiar_texto_ficha(self.version)

    # --- valores canónicos derivados ---
    def c_marca(self):
        m = compacto(self.marca)
        return ALIAS_MARCA.get(m, m)

    def c_anio(self):
        return parse_entero(self.anio)

    def c_comb(self):
        return canon_combustible(self.combustible)

    def c_trans(self):
        return canon_transmision(self.transmision) or transmision_desde_texto(self.version)

    def c_trac(self):
        return traccion_desde_texto(self.traccion, self.version, self.modelo)

    def c_cc(self):
        return parse_cilindrada(self.cilindrada)

    def c_cc_version(self):
        """Cilindrada escrita en la versión (ej. '1.6 GLS')."""
        m = re.search(r"\b(\d\.\d)\b", normalizar_texto(self.version))
        return parse_cilindrada(m.group(1)) if m else None

    def c_puertas(self):
        return parse_entero(self.puertas)

    def c_tipos(self):
        return TIPO_MAIA_A_SII.get(compacto(self.tipo), {compacto(self.tipo)} if self.tipo else set())


# ---------------------------------------------------------------------------
# Similitudes (0..1)
# ---------------------------------------------------------------------------
def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio() if a and b else 0.0


def sim_marca(marca_c: str, fila_marca_c: str) -> float:
    if not marca_c or not fila_marca_c:
        return 0.0
    if marca_c == fila_marca_c:
        return 1.0
    if fila_marca_c.startswith(marca_c) or marca_c.startswith(fila_marca_c) \
            or fila_marca_c.endswith(marca_c) or marca_c.endswith(fila_marca_c):
        return 0.9
    r = _ratio(marca_c, fila_marca_c)
    return r if r >= 0.85 else 0.0


def sim_modelo(modelo: str, fila) -> float:
    m_c = compacto(modelo)
    if not m_c:
        return 0.0
    f_c = fila["_modelo_c"]
    if m_c == f_c:
        return 1.0
    t_api = frozenset(tokens(modelo))
    t_sii = fila["_modelo_t"]
    # Uno contiene al otro: 'H7L' vs 'H7', 'GRAND VITARA' vs 'VITARA'
    if f_c and (m_c in f_c or f_c in m_c):
        corto, largo = sorted([m_c, f_c], key=len)
        return 0.75 + 0.2 * (len(corto) / len(largo))
    comunes = t_api & t_sii
    if comunes:
        return 0.55 + 0.4 * len(comunes) / max(len(t_api | t_sii), 1)
    r = _ratio(m_c, f_c)
    return r * 0.8 if r >= 0.7 else 0.0


def sim_modelo_ext(modelo: str, fila, tok_modelo: frozenset, desc_t: frozenset = frozenset()) -> float:
    """
    Como sim_modelo, pero además acepta:
      * que el modelo de la ficha aparezca en la VERSIÓN SII
        (ficha 'Y3' vs SII modelo 'AEOLUS' versión 'Y3 AT CONFORT');
      * que el modelo SII esté contenido en modelo + versión de la ficha
        (SII 'C-1119' vs ficha modelo 'CARGO' versión '1119').
    """
    s = sim_modelo(modelo, fila)
    sii_sig = {t for t in fila["_modelo_t"]
               if (t.isdigit() and len(t) >= 2) or (len(t) >= 3 and not re.fullmatch(r"\d+\.\d+", t))}
    if sii_sig and desc_t and sii_sig <= desc_t:
        s = max(s, 0.85)
    if s < 0.6 and tok_modelo and (tok_modelo & fila["_version_t"]):
        return 0.6
    return s


def sim_version(desc_tokens: frozenset, ver_c: str, fila):
    """
    Similitud de versión. Se compara TODO lo que la ficha dice más allá del modelo
    de la fila SII (modelo + versión de la ficha, menos los tokens del modelo SII).
    Así 'AEOLUS Y3 1.5' + '...' calza con modelo SII 'AEOLUS' versión 'Y3 AT CONFORT'.
    Devuelve None si la ficha no aporta información de versión.
    """
    f_c = fila["_version_c"]
    if ver_c and f_c and ver_c == f_c:
        return 1.0                                   # versión idéntica
    ver_tokens = desc_tokens - fila["_modelo_t"]
    if not ver_tokens:
        return None
    f_t = fila["_version_t"]
    if not f_t:
        return None          # la fila SII no trae versión (ej. 'SIN VERSION'): no se puede comparar
    comunes = ver_tokens & f_t
    # Coincidencias parciales de códigos (ej. 'GLS' vs 'GLSA', 'EG10' vs 'EG10A')
    parciales = sum(
        1 for a in ver_tokens - comunes
        if len(a) >= 3 and any((b.startswith(a) or a.startswith(b)) and len(b) >= 3 for b in f_t - comunes)
    )
    # Coeficiente de Dice: premia coincidir en todos los tokens de AMBOS lados
    dice = 2 * (len(comunes) + 0.5 * parciales) / (len(ver_tokens) + len(f_t))
    if ver_tokens == f_t:
        return 0.97                                  # mismos tokens, distinto orden/puntuación
    return min(0.93, dice)


def sim_cilindrada(cc: int | None, fila_cc) -> float | None:
    if not cc or fila_cc is None or pd.isna(fila_cc):
        return None
    d = abs(cc - int(fila_cc))
    if d <= 60:
        return 1.0
    if d <= 150:
        return 0.6
    if d <= 300:
        return 0.2
    return 0.0


# ---------------------------------------------------------------------------
# Resultado
# ---------------------------------------------------------------------------
@dataclass
class Resultado:
    metodo: str                          # "codigo_validado" | "caracteristicas" | "sin_resultado"
    mensaje: str
    candidatos: pd.DataFrame = field(default_factory=pd.DataFrame)
    confianza: str = ""                  # Alta / Media / Baja
    advertencias: list[str] = field(default_factory=list)

    @property
    def mejor(self):
        return None if self.candidatos.empty else self.candidatos.iloc[0]


def _puntuar(v: Vehiculo, fila, pre) -> tuple[float, dict]:
    detalle, obtenido, posible = {}, 0.0, 0.0

    def sumar(nombre, sim):
        nonlocal obtenido, posible
        if sim is None:
            return
        detalle[nombre] = round(sim * 100)
        obtenido += sim * PESOS[nombre]
        posible += PESOS[nombre]

    sumar("marca", sim_marca(pre["marca"], fila["_marca_c"]) if pre["marca"] else None)
    sumar("modelo", sim_modelo_ext(v.modelo, fila, pre["mod_t"], pre["desc_t"]) if pre["modelo"] else None)
    sumar("version", sim_version(pre["desc_t"], pre["ver_c"], fila))
    if pre["trans"] and fila["_trans"]:
        sumar("transmision", 1.0 if pre["trans"] == fila["_trans"] else 0.0)
    if pre["comb"] and fila["_comb"]:
        sumar("combustible", 1.0 if pre["comb"] == fila["_comb"] else 0.0)
    cc = pre["cc"] or pre["cc_version"]
    sumar("cilindrada", sim_cilindrada(cc, fila["_cc"]))
    if pre["trac"] and fila["_trac"]:
        sumar("traccion", 1.0 if pre["trac"] & fila["_trac"] else 0.0)
    if pre["puertas"] and fila["_puertas"] and not pd.isna(fila["_puertas"]):
        sumar("puertas", 1.0 if int(pre["puertas"]) == int(fila["_puertas"]) else 0.0)
    if pre["tipos"] and fila["_tipo"]:
        sumar("tipo", 1.0 if fila["_tipo"] in pre["tipos"] else 0.0)

    if posible == 0:
        return 0.0, detalle
    # Se re-escala a 100, pero con un piso de evidencia: si solo se pudo comparar
    # poco (ej. solo marca+modelo), el puntaje no puede llegar a 100.
    cobertura = min(1.0, posible / 70)
    return round(100 * obtenido / posible * (0.6 + 0.4 * cobertura), 1), detalle


def _preprocesar(v: Vehiculo) -> dict:
    return {
        "marca": v.c_marca(),
        "modelo": compacto(v.modelo),
        "ver_t": tokens_version(v.version),
        "mod_t": tokens_version(v.modelo),
        "desc_t": tokens_version(f"{v.modelo} {v.version}"),
        "ver_c": compacto(v.version),
        "trans": v.c_trans(),
        "comb": v.c_comb(),
        "cc": v.c_cc(),
        "cc_version": v.c_cc_version(),
        "trac": v.c_trac(),
        "puertas": v.c_puertas(),
        "tipos": v.c_tipos(),
    }


def _confianza(candidatos: pd.DataFrame) -> str:
    if candidatos.empty:
        return ""
    s1 = candidatos.iloc[0]["Puntaje"]
    s2 = candidatos.iloc[1]["Puntaje"] if len(candidatos) > 1 else 0
    # Empate con tasaciones distintas: no se puede asegurar el avalúo
    empatados = candidatos[candidatos["Puntaje"] >= s1 - 2]
    if len(empatados) > 1 and empatados[COL_TASACION].nunique() > 1:
        return "Media" if s1 >= 85 else "Baja"
    # Sin versión exacta no hay confianza alta si otras versiones tasan distinto
    simver = candidatos.iloc[0].get("_simver")
    otras_tasaciones = candidatos[COL_TASACION].nunique() > 1
    if otras_tasaciones and (simver is None or pd.isna(simver) or simver < 90):
        return "Media" if s1 >= 70 else "Baja"
    misma_tasacion = len(candidatos) > 1 and \
        candidatos.iloc[0][COL_TASACION] == candidatos.iloc[1][COL_TASACION]
    if s1 >= 85 and (s1 - s2 >= 4 or misma_tasacion):
        return "Alta"
    if s1 >= 70:
        return "Media"
    return "Baja"


def _formatear(df: pd.DataFrame) -> pd.DataFrame:
    cols = ["Puntaje"] + COLUMNAS_SALIDA + ["Detalle puntaje"]
    return df[[c for c in cols if c in df.columns]].reset_index(drop=True)


def buscar_por_caracteristicas(base: pd.DataFrame, v: Vehiculo, top: int = 10) -> Resultado:
    advertencias = []
    anio = v.c_anio()
    if not anio:
        return Resultado("sin_resultado", "Falta el año del vehículo: la tasación SII es por año.")
    if not compacto(v.marca) or not compacto(v.modelo):
        return Resultado("sin_resultado", "Faltan marca y/o modelo para buscar por características.")

    pre = _preprocesar(v)
    del_anio = base[base["_anio"] == anio]
    if del_anio.empty:
        return Resultado("sin_resultado", f"La base SII no tiene vehículos del año {anio}.")

    if compacto(v.marca) != pre["marca"]:
        marca_sii = del_anio.loc[del_anio["_marca_c"] == pre["marca"], COL_MARCA]
        if not marca_sii.empty:
            advertencias.append(f"La marca '{v.marca}' se interpretó como '{marca_sii.iloc[0]}' (equivalencia de marcas).")

    def filtrar_modelo(df, minimo):
        sims = df.apply(lambda f: sim_modelo_ext(v.modelo, f, pre["mod_t"], pre["desc_t"]), axis=1)
        return df[sims >= minimo]

    # 1) Marca + modelo
    sim_m = del_anio["_marca_c"].map(lambda x: sim_marca(pre["marca"], x))
    por_marca = del_anio[sim_m > 0]
    cand = filtrar_modelo(por_marca, 0.5) if not por_marca.empty else por_marca
    respaldo = False

    # La marca existe pero el modelo no: se informan los modelos disponibles de esa marca
    if cand.empty and not por_marca.empty:
        modelos = por_marca[COL_MODELO].value_counts().index.tolist()
        return Resultado(
            "sin_resultado",
            f"No se encontró el modelo '{v.modelo}' de {v.marca} año {anio} en la base SII. "
            f"Modelos {v.marca.upper()} {anio} disponibles: {', '.join(sorted(modelos)[:25])}"
            f"{' …' if len(modelos) > 25 else ''}. Revise si el modelo está en el campo Versión.",
            advertencias=advertencias)

    # 2) Respaldo: la marca no existe; buscar el modelo en TODAS las marcas
    if cand.empty:
        claves = [t for t in pre["mod_t"] if len(t) >= 2 and not t.isdigit()]
        if claves:
            patron = "|".join(re.escape(compacto(t)) for t in claves)
            texto = del_anio["_modelo_c"] + " " + del_anio["_version_c"]
            pre_filtro = del_anio[texto.str.contains(patron, regex=True)]
            cand = filtrar_modelo(pre_filtro, 0.6) if not pre_filtro.empty else pre_filtro
        if cand.empty:
            if por_marca.empty:
                msg = (f"No hay vehículos marca '{v.marca}' del año {anio} en la base SII, ni el modelo "
                       f"'{v.modelo}' en otra marca. Revise marca/modelo o agregue la equivalencia en "
                       f"{ARCHIVO_ALIAS_MARCAS}.")
            else:
                msg = f"No se encontró el modelo '{v.modelo}' de {v.marca} año {anio} en la base SII."
            return Resultado("sin_resultado", msg, advertencias=advertencias)
        respaldo = True
        marcas = ", ".join(cand[COL_MARCA].value_counts().index[:5])
        advertencias.append(
            f"La marca '{v.marca}' no aparece en la base SII {anio}"
            f"{' con ese modelo' if not por_marca.empty else ''}. Se muestran coincidencias del "
            f"modelo en: {marcas}. Verifique la marca; si es la misma, agréguela en {ARCHIVO_ALIAS_MARCAS}."
        )
        pre = dict(pre, marca="")          # la marca no puntúa en el respaldo

    # Si la ficha indica tipo, se prioriza la base correspondiente sin excluir la otra
    puntajes, detalles = [], []
    for _, fila in cand.iterrows():
        p, d = _puntuar(v, fila, pre)
        puntajes.append(p)
        detalles.append(d)
    cand = cand.copy()
    cand["Puntaje"] = puntajes
    cand["_simver"] = [d.get("version") for d in detalles]
    cand["Detalle puntaje"] = [
        ", ".join(f"{k} {val}%" for k, val in d.items()) for d in detalles
    ]
    # Datos de la ficha que no calzan con NINGUNA versión del modelo: probablemente vienen mal
    columnas = {"cilindrada": COL_CC, "combustible": COL_COMB, "transmision": "_trans"}
    for campo, nombre, valor in [("cilindrada", "cilindrada", v.cilindrada),
                                 ("combustible", "combustible", v.combustible),
                                 ("transmision", "transmisión", v.transmision)]:
        vals = [d[campo] for d in detalles if campo in d]
        if vals and len(vals) == len(detalles) and max(vals) == 0:
            valores_sii = sorted(set(cand[columnas[campo]]) - {""})
            advertencias.append(
                f"La {nombre} de la ficha ({valor or 'deducida de la versión'}) no coincide con ninguna "
                f"versión de este modelo en la base SII ({', '.join(valores_sii[:4])}). Verifique el dato."
            )
    cand = cand.sort_values(["Puntaje", "_tasacion"], ascending=[False, True]).head(top)

    # Advertencias útiles para el usuario
    faltan = [n for n, val in [("versión", v.version), ("transmisión", v.transmision),
                               ("combustible", v.combustible), ("cilindrada", v.cilindrada)]
              if not str(val).strip()]
    if faltan:
        advertencias.append("Para mayor precisión complete: " + ", ".join(faltan) + ".")
    if len(cand) > 1:
        empatados = cand[cand["Puntaje"] >= cand.iloc[0]["Puntaje"] - 2]
        if len(empatados) > 1 and empatados["_tasacion"].nunique() > 1:
            mn, mx = empatados["_tasacion"].min(), empatados["_tasacion"].max()
            advertencias.append(
                f"{len(empatados)} versiones quedan casi empatadas; la tasación varía entre "
                f"${mn:,.0f} y ${mx:,.0f}. Revise la versión exacta.".replace(",", ".")
            )

    res = Resultado("caracteristicas", "Búsqueda por características.",
                    _formatear(cand), advertencias=advertencias)
    res.confianza = _confianza(cand)
    if respaldo and res.confianza == "Alta":
        res.confianza = "Media"             # la marca no se pudo confirmar
    return res


def validar_codigo(base: pd.DataFrame, v: Vehiculo) -> Resultado | None:
    """
    Si viene un Código SII (ej. desde GetAPI), se busca ese código y año y se
    verifica que sea coherente con la ficha. Devuelve None si no se puede validar.
    """
    codigo = str(v.codigo_sii or "").strip().upper()
    anio = v.c_anio()
    if not codigo or not anio:
        return None
    filas = base[(base["_codigo"] == codigo) & (base["_anio"] == anio)]
    if filas.empty:
        return None
    pre = _preprocesar(v)
    fila = filas.iloc[0]

    # Chequeos de coherencia (solo cuentan cuando ambos lados tienen el dato)
    conflictos = []
    if pre["marca"] and sim_marca(pre["marca"], fila["_marca_c"]) == 0:
        conflictos.append("marca")
    if pre["modelo"] and sim_modelo_ext(v.modelo, fila, pre["mod_t"], pre["desc_t"]) < 0.5:
        conflictos.append("modelo")
    if pre["trans"] and fila["_trans"] and pre["trans"] != fila["_trans"]:
        conflictos.append("transmisión")
    if pre["comb"] and fila["_comb"] and pre["comb"] != fila["_comb"]:
        conflictos.append("combustible")
    cc = pre["cc"] or pre["cc_version"]
    s_cc = sim_cilindrada(cc, fila["_cc"])
    if s_cc is not None and s_cc < 0.6:
        conflictos.append("cilindrada")
    if conflictos:
        return Resultado("codigo_rechazado",
                         f"El Código SII {codigo} no coincide con la ficha en: {', '.join(conflictos)}.")

    p, d = _puntuar(v, fila, pre)
    df = filas.head(1).copy()
    df["Puntaje"] = max(p, 90.0)
    df["Detalle puntaje"] = "Código SII validado contra la ficha; " + ", ".join(f"{k} {x}%" for k, x in d.items())
    return Resultado("codigo_validado", f"Código SII {codigo} validado.", _formatear(df), confianza="Alta")


def tasar(base: pd.DataFrame, v: Vehiculo, top: int = 10) -> Resultado:
    """Punto de entrada: primero valida el Código SII (si viene); si no, busca por características."""
    advertencias = []
    val = validar_codigo(base, v)
    if val is not None and val.metodo == "codigo_validado":
        # Se agregan alternativas por características como referencia
        alt = buscar_por_caracteristicas(base, v, top)
        if not alt.candidatos.empty:
            extra = alt.candidatos[alt.candidatos[COL_CODIGO].str.upper() != v.codigo_sii.strip().upper()]
            val.candidatos = pd.concat([val.candidatos, extra], ignore_index=True).head(top)
        return val
    if val is not None:
        advertencias.append(val.mensaje + " Se buscó por características.")
    elif v.codigo_sii:
        advertencias.append(
            f"El Código SII {v.codigo_sii} no existe para el año {v.anio} en la base; se buscó por características."
        )
    res = buscar_por_caracteristicas(base, v, top)
    res.advertencias = advertencias + res.advertencias
    return res
