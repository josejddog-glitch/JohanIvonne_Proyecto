"""Pre-detección heurística de tipologías en Python para acelerar al modelo.

Cada tipología tiene palabras clave; contamos coincidencias en el texto del
expediente (OCR) y retornamos las top-N tipologías candidatas con sus bloques
relevantes. Claude recibe solo esos bloques inline, sin tener que leer todo
el directorio `bloques/` ni `tipologias.md`.

Falsos positivos / negativos son tolerables: Claude valida en su razonamiento.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BLOQUES_DIR = ROOT / "knowledge" / "bloques"


# Tabla manual basada en knowledge/tipologias.md (se mantiene en sincronía con ese archivo).
TIPOLOGIAS = [
    {
        "nombre": "Pérdida de número celular en prepago",
        "bloques": ["perdida_numero_prepago.md"],
        "kw": [
            r"\binactividad\b", r"\bdesactivad", r"\bcuarentena\b",
            r"\bdías de inactividad\b", r"\bsin recargas?\b",
            r"\bnúmero (celular|móvil) (prepago|cancelad)",
            r"\bperdid[ao] (la|el) (línea|número)",
            r"\bp[eé]rdida del? n[uú]mero\b",
        ],
    },
    {
        "nombre": "Promociones / ofertas / descuentos no aplicados",
        "bloques": ["deber_informacion.md", "promociones_ofertas.md"],
        "kw": [
            r"\bpromoci[oó]n", r"\bdescuento", r"\boferta",
            r"\bel asesor (me )?(dijo|inform[oó]|prometi[oó])",
            r"\bbeneficio (no aplicad[oa]|otorgad[oa])",
            r"\bduraci[oó]n de la (oferta|promoci[oó]n)",
        ],
    },
    {
        "nombre": "Plan no aplicado / condiciones contractuales incumplidas",
        "bloques": ["deber_informacion.md"],
        "kw": [
            r"\bno me (dieron|aplicaron) (lo que )?contrat[eé]",
            r"\brenta (diferente|mayor|menor)",
            r"\bservicio adicional no solicitad",
            r"\bdecodificador adicional",
            r"\bcondiciones (ofrecidas|del plan)",
        ],
    },
    {
        "nombre": "Parrilla de canales TV modificada",
        "bloques": ["deber_informacion.md", "parrilla_canales_tv.md"],
        "kw": [
            r"\bcanal(es)? (eliminad|retirad|sustituid)",
            r"\bparrilla\b", r"\btelevisi[oó]n",
            r"\bcanales premium", r"\bClaro TV\b", r"\bDirecTV\b",
            r"\bplan de televisi[oó]n",
        ],
    },
    {
        "nombre": "Gestión de cobranza / casas de cobro",
        "bloques": ["procedencia_recursos_ley1341.md"],
        "kw": [
            r"\bcasa de cobranza", r"\bcobro coactivo",
            r"\bllamadas? de cobro", r"\bgesti[oó]n de cobr",
            r"\bme cobran (mientras|aunque)",
        ],
    },
    {
        "nombre": "Reporte negativo en centrales de riesgo",
        "bloques": ["procedencia_recursos_ley1341.md", "traslado_habeas_data.md"],
        "kw": [
            r"\bDataCr[eé]dito\b", r"\bCIFIN\b",
            r"\bcentrales? de riesgo", r"\breporte negativo",
            r"\bhabeas data\b", r"\bCovinoc\b",
        ],
    },
    {
        "nombre": "Cobros por equipos en comodato / devolución",
        "bloques": ["procedencia_recursos_ley1341.md"],
        "kw": [
            r"\bcomodato\b", r"\bdecodificador no entregad",
            r"\bno devolv[ií] el equipo", r"\bequipo en (préstamo|comodato)",
        ],
    },
    {
        "nombre": "Cancelación del servicio",
        "bloques": ["cancelacion.md"],
        "kw": [
            r"\bsolicit[eé] la cancelaci[oó]n",
            r"\bterminaci[oó]n del contrato",
            r"\bcancelar el servicio",
            r"\bsiguen cobrando despu[eé]s de cancelar",
        ],
    },
    {
        "nombre": "Cláusula de permanencia",
        "bloques": ["permanencia.md"],
        "kw": [
            r"\bpermanencia\b", r"\bpenalizaci[oó]n",
            r"\bmulta por cancelar", r"\bcl[aá]usula\b",
            r"\bsubsidio del? equipo", r"\btermin[oó] anticipad",
        ],
    },
    {
        "nombre": "Portabilidad numérica móvil",
        "bloques": ["portabilidad.md"],
        "kw": [
            r"\bportabilidad\b", r"\bporting\b", r"\bport[ -]?out\b", r"\bport[ -]?in\b",
            r"\bcambio de operador", r"\bno me dejan portar",
            r"\bporting rechazad",
        ],
    },
    {
        "nombre": "Calidad del servicio (cortes, intermitencia)",
        "bloques": ["calidad_servicio.md"],
        "kw": [
            r"\bcortes? del servicio", r"\bno funciona", r"\bintermitencia",
            r"\blent[oa]\b", r"\bsin se[ñn]al", r"\binternet ca[ií]d",
            r"\bcompensaci[oó]n por (corte|falla)",
        ],
    },
]


@dataclass
class TipologiaDetectada:
    nombre: str
    bloques: list[str] = field(default_factory=list)
    score: int = 0
    matches: list[str] = field(default_factory=list)


def detectar(texto_ocr: str, top_n: int = 3) -> list[TipologiaDetectada]:
    """Detecta las top-N tipologías más probables según matches de keywords."""
    if not texto_ocr:
        return []
    texto = texto_ocr.lower()

    candidatos: list[TipologiaDetectada] = []
    for t in TIPOLOGIAS:
        matches: list[str] = []
        for kw in t["kw"]:
            for m in re.finditer(kw, texto, re.IGNORECASE):
                matches.append(m.group(0))
        if matches:
            candidatos.append(TipologiaDetectada(
                nombre=t["nombre"],
                bloques=t["bloques"],
                score=len(matches),
                matches=list({m.lower() for m in matches})[:5],
            ))
    candidatos.sort(key=lambda x: x.score, reverse=True)
    return candidatos[:top_n]


def cargar_bloques_aplicables(detectadas: list[TipologiaDetectada]) -> dict[str, str]:
    """Lee y retorna el contenido de los bloques únicos referidos por las tipologías."""
    nombres_unicos: list[str] = []
    for t in detectadas:
        for b in t.bloques:
            if b not in nombres_unicos:
                nombres_unicos.append(b)
    out: dict[str, str] = {}
    for nombre in nombres_unicos:
        path = BLOQUES_DIR / nombre
        if path.exists():
            out[nombre] = path.read_text(encoding="utf-8")
    return out
