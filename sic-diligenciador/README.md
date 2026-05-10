# SIC Diligenciador

Herramienta semi-automática para redactar borradores de resoluciones de apelación de la SIC (sector comunicaciones) a partir del expediente y los anexos del caso.

## Cómo correrla

### Primera vez

```bat
cd C:\Daniel\JOHAN_IVONNE\sic-diligenciador
pip install -r requirements.txt
```

Verifica que tengas Claude Code instalado y sesión Pro activa:
```bat
claude --version
```

### Cada vez (3 maneras de arrancar — elige la que prefieras)

| Forma | Cómo | Ventana negra | Build previo |
|---|---|---|---|
| **`run.bat`** | Doble-clic | Sí (cmd) | No |
| **`iniciar.vbs`** | Doble-clic | **No** (oculta) | No |
| **`iniciar.exe`** | Doble-clic | **No** | Sí (corre `build_exe.bat` una vez, ~10 min) |

Las tres opciones abren automáticamente `http://localhost:8000` en tu navegador. Con `iniciar.vbs` ó `iniciar.exe`, para detener el servidor doble-clic en `detener.vbs` (o desde el Administrador de Tareas: matar `python.exe` o `iniciar.exe`).

> **Nota:** la "página" que se abre es HTML servido por un mini servidor Flask **local** (`localhost`). Tus archivos NO se suben a internet. Lo único que sale a Anthropic es el contenido del expediente que Claude analiza (eso ya lo sabías).

## Flujo de uso (un caso)

1. Sube el expediente (PDF) y, si los hay, anexos (PDFs, DOCX) y audios (MP3/WAV).
2. Pulsa **Diligenciar**. Espera 5–15 minutos según tamaño y cantidad de audios.
3. Descarga `resolucion_diligenciada.docx` y `resumen.md`.
4. **Revisa** el `.docx` y atiende los marcadores `[VERIFICAR: ...]`.
5. Si algo no quedó bien, en la misma página puedes:
   - **Regenerar con observaciones** — escribes qué cambiar y la IA reelabora.
   - **Enviar feedback** — registras qué tan bien quedó (alimenta la calibración).

## Fase 2 — Calibración con casos reales

A medida que uses la herramienta, cada caso queda registrado:

- **`audit.csv`** — métricas operativas (duración, tipologías detectadas, bloques usados, sentido sugerido, marcadores `[VERIFICAR]`).
- **`feedback.jsonl`** — feedback humano que envíes desde la página del caso.

Después de procesar 5–10 casos reales, corre:

```bat
python tools\calibrar.py
```

Esto genera `tools/reporte_calibracion.md` con:
- Tasa de acierto del sentido propuesto.
- Calidad promedio reportada.
- Tipologías y bloques más frecuentes.
- Secciones problemáticas más reportadas.
- Bloques faltantes que mencionaste.
- Sugerencias automáticas de qué ajustar.

Con ese reporte tú (o yo en una próxima sesión) editamos:
- `prompts/caso.md.j2` — para reforzar reglas si la IA falla en algo recurrente.
- `knowledge/tipologias.md` — para afinar palabras clave y mapeos.
- `knowledge/bloques/*.md` — para corregir o crear bloques nuevos.
- `CLAUDE.md` — para reglas duras adicionales.

## Tests golden (Fase 3)

Para verificar que la herramienta sigue funcionando bien con los 4 ejemplos validados:

```bat
python tests\golden\run_golden.py            # corre los 4
python tests\golden\run_golden.py --solo ejemplo_original   # solo uno
```

Reporta para cada ejemplo: sentido acertado, similitud Jaccard contra la solución real, marcadores `[VERIFICAR]`. Útil tras cada cambio significativo a prompts o bloques.

## Estructura

```
sic-diligenciador/
├── app.py                    # Flask: /, /upload, /status, /caso, /regenerar, /feedback, /download
├── pipeline.py               # Orquestación
├── claude_runner.py          # Wrapper de Claude Code CLI
├── audio_transcribe.py       # Whisper local (faster-whisper) con timestamps
├── file_classifier.py        # Detecta expediente vs anexos vs audios
├── auditoria.py              # CSV global de casos procesados
├── feedback_log.py           # JSONL de feedback humano
├── CLAUDE.md                 # Sistema/rol/reglas duras (auto-cargado por Claude Code)
├── prompts/
│   └── caso.md.j2            # Plantilla del prompt por caso
├── knowledge/
│   ├── plantilla.docx        # Plantilla en blanco
│   ├── manual_sic.docx       # Manual oficial
│   ├── frases_ancla.md       # Frases literales por numeral
│   ├── tipologias.md         # Tabla de tipologías → bloques
│   ├── reglas_extraidas.md   # Reglas duras del manual
│   ├── bloques/              # 11 bloques jurídicos por tema
│   │   ├── deber_informacion.md
│   │   ├── promociones_ofertas.md
│   │   ├── perdida_numero_prepago.md
│   │   ├── parrilla_canales_tv.md
│   │   ├── procedencia_recursos_ley1341.md
│   │   ├── acumulacion_expedientes.md
│   │   ├── traslado_habeas_data.md
│   │   ├── cancelacion.md           (NOTA: validar en Fase 2 con caso real)
│   │   ├── permanencia.md           (NOTA: validar en Fase 2 con caso real)
│   │   ├── portabilidad.md          (NOTA: validar en Fase 2 con caso real)
│   │   └── calidad_servicio.md      (NOTA: validar en Fase 2 con caso real)
│   └── ejemplos/             # 4 ejemplos diligenciados (referencia y golden tests)
├── workspaces/               # Carpetas temporales por caso (uno por upload)
├── tests/golden/run_golden.py # Test contra los 4 ejemplos
├── tools/calibrar.py         # Genera reporte de calibración
├── audit.csv                 # (se crea solo) métricas por caso
├── feedback.jsonl            # (se crea solo) feedback humano
├── requirements.txt
├── run.bat
└── README.md
```

## Cómo agregar una nueva tipología

1. Crear `knowledge/bloques/<tema>.md` con el texto literal del marco normativo.
2. Agregar fila en `knowledge/tipologias.md` con palabras clave y bloques aplicables.
3. (Opcional) ajustar `CLAUDE.md` si la tipología tiene reglas especiales.
4. Validar con `python tests/golden/run_golden.py` que no se rompió nada.

## Optimización de tiempos

Tiempos típicos por caso:
- **Simple** (PDF ~10 pág, sin audio): 5–8 min
- **Típico** (PDF 20 pág + 2–4 anexos + 1 audio 5 min): 12–20 min
- **Pesado** (PDF 50 pág + 5 anexos + audio 15 min): 25–40 min

### Optimizaciones ya activas (sin acción tuya)

- **Auto-pick de modelo Whisper según duración:**
  - Audios ≤ 20 min: modelo `small` sin chunking.
  - Audios > 20 min: modelo `base` + chunking en bloques de 10 min con overlap de 5 s, transcritos en paralelo (4 workers). Medido: **~2.6× más rápido** sin pérdida de calidad relevante para uso jurídico.
- **Paralelización entre archivos**: hasta 2 audios distintos al tiempo.
- **Caché** de transcripciones por hash MD5 (re-procesos instantáneos).
- VAD (saltar silencios) + cuantización int8.

Variables para sobreescribir:
```bat
set SIC_WHISPER_MODEL=medium          REM modelo para audios cortos
set SIC_WHISPER_MODEL_LARGO=small     REM modelo para audios >20 min (más calidad, más lento)
```

### Para forzar otra calidad de Whisper

Cambia la variable de entorno antes de arrancar:
```bat
set SIC_WHISPER_MODEL=medium    REM más preciso, ~3x más lento
set SIC_WHISPER_MODEL=tiny      REM ultra rápido, baja calidad (solo para tests)
iniciar.vbs
```

### OCR previo con Tesseract (ACTIVO)

Implementado y funcionando. Cuando subes un PDF, el pipeline detecta si es escaneado y lo pasa por Tesseract+Poppler antes de enviarlo a Claude. Resultado: **~7× más rápido** en PDFs escaneados (medido: 20 páginas pasan de ~12 min a ~1.8 min).

- Binario Tesseract: `C:\Program Files\Tesseract-OCR\tesseract.exe` (instalado vía winget)
- Poppler: ubicación de winget (`oschwartz10612.Poppler`)
- Idioma español: `bin/tessdata/spa.traineddata` (descargado de tessdata_best, ~13 MB)
- Caché por hash MD5: re-procesar el mismo PDF es instantáneo (`cache/ocr/`)

Si en algún momento Tesseract falla o no está disponible, el pipeline sigue funcionando — Claude lee el PDF vía visión como antes.

Para sobreescribir rutas:
```bat
set SIC_TESSERACT_EXE=C:\otra\ruta\tesseract.exe
set SIC_POPPLER_BIN=C:\otra\ruta\poppler\bin
set SIC_TESSDATA_DIR=C:\otra\ruta\tessdata
```

### Si tienes GPU NVIDIA

`faster-whisper` con CUDA es 10–30× más rápido. Cambia `device="cpu"` por `device="cuda"` en `audio_transcribe.py:65`.

## Limitaciones conocidas

- **Cuota Claude Pro:** con >15 casos/semana podría agotarse. Mide consumo desde `audit.csv` (columna `duracion_seg`) y considera Claude Max o pasar a API si es necesario.
- **Tiempo por caso:** 5–15 min típico, hasta 25 min con muchos audios largos. Whisper en CPU es el cuello de botella en audios.
- **Bloques marcados "validar en Fase 2"** (cancelación, permanencia, portabilidad, calidad): se construyeron a partir del marco normativo general; necesitan validarse contra al menos un caso real cada uno.
- **Anonimización:** no implementada. Si en algún momento se requiere, se puede agregar paso previo (Tesseract + regex/NER) antes de invocar a Claude.

## Ciclo recomendado durante Fase 2

Por cada caso:
1. Subes archivos → recibes borrador → revisas.
2. Si quedó bien: descargas, firmas, **envías feedback positivo** (calidad 4-5).
3. Si quedó parcial: usas **regenerar con observaciones** (1-2 iteraciones suelen bastar).
4. Si encontraste un bloque nuevo necesario: lo escribes en el campo "bloques faltantes" del feedback.

Cada viernes o cada 10 casos: corre `python tools/calibrar.py` y revisa el reporte. Si hay un patrón claro (sentido fallando en una tipología, bloque mal seleccionado, etc.), ajusta los archivos correspondientes y verifica con los golden tests.
