"""Clasifica los archivos de un caso en: expediente principal, anexos PDF/DOCX, audios."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

PDF_EXTS = {".pdf"}
DOC_EXTS = {".docx", ".doc"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}


@dataclass
class ClasificacionCaso:
    expediente_principal: Path | None = None
    anexos_pdf: list[Path] = field(default_factory=list)
    anexos_doc: list[Path] = field(default_factory=list)
    audios: list[Path] = field(default_factory=list)
    otros: list[Path] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "expediente_principal": str(self.expediente_principal) if self.expediente_principal else None,
            "anexos_pdf": [str(p) for p in self.anexos_pdf],
            "anexos_doc": [str(p) for p in self.anexos_doc],
            "audios": [str(p) for p in self.audios],
            "otros": [str(p) for p in self.otros],
        }


def _contar_paginas_pdf(pdf_path: Path) -> int:
    try:
        from pypdf import PdfReader
        return len(PdfReader(str(pdf_path)).pages)
    except Exception:
        return 0


def clasificar(archivos: list[Path]) -> ClasificacionCaso:
    """Recibe una lista de Paths y los clasifica.

    Heurística para detectar el expediente principal:
      1. Si algún PDF tiene en el nombre la palabra 'expediente' (case-insensitive), ese es.
      2. Si no, el PDF con más páginas.
      3. El resto de PDFs son anexos.
    """
    resultado = ClasificacionCaso()
    pdfs: list[Path] = []

    for f in archivos:
        ext = f.suffix.lower()
        if ext in PDF_EXTS:
            pdfs.append(f)
        elif ext in DOC_EXTS:
            resultado.anexos_doc.append(f)
        elif ext in AUDIO_EXTS:
            resultado.audios.append(f)
        else:
            resultado.otros.append(f)

    if pdfs:
        nombrados = [p for p in pdfs if "expediente" in p.stem.lower()]
        if nombrados:
            principal = max(nombrados, key=lambda p: _contar_paginas_pdf(p))
        else:
            principal = max(pdfs, key=lambda p: _contar_paginas_pdf(p))
        resultado.expediente_principal = principal
        resultado.anexos_pdf = [p for p in pdfs if p != principal]

    return resultado
