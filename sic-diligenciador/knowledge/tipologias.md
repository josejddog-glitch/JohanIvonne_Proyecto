# Tipologías de caso → bloques aplicables

Tabla de decisión para que la herramienta seleccione qué bloques jurídicos insertar en el numeral CUARTO según los hechos del caso. **Un caso puede tener varias tipologías simultáneas** (cada una se redacta como subsección 4.1, 4.2, ...).

---

## Cómo usar esta tabla

1. Lee el expediente y los anexos.
2. Identifica las **pretensiones** del usuario (puede haber varias).
3. Por cada pretensión, busca la tipología que mejor encaja (palabras clave).
4. Inserta los bloques correspondientes en orden.
5. Si una pretensión no encaja en ninguna tipología, redactar la subsección desde cero pero seguir las pautas del manual y marcar `[VERIFICAR: tipología no estándar – {descripción}]` en `resumen.md`.

---

## Tabla

| # | Tipología | Palabras clave en el expediente | Bloques a usar (en orden) | Sentido típico |
|---|---|---|---|---|
| 1 | **Pérdida de número celular en prepago** | "línea desactivada", "inactividad", "no usé la línea", "número reasignado", "cuarentena", "sin recargas" | `perdida_numero_prepago.md` | CONFIRMA si hubo aviso previo y >2 meses sin uso; REVOCA si no hay aviso |
| 2 | **Promociones / ofertas / descuentos no aplicados** | "promoción", "descuento", "oferta", "no me aplicaron el beneficio", "duración de la oferta", "el asesor me dijo" | `deber_informacion.md` + `promociones_ofertas.md` | CONFIRMA si el contrato magnetofónico contiene los términos correctos; REVOCA/MODIFICA si hay contradicción |
| 3 | **Plan no aplicado / condiciones contractuales incumplidas** | "no me dieron lo que contraté", "renta diferente a la pactada", "servicio adicional no solicitado", "decodificador adicional" | `deber_informacion.md` + (si es TV) `parrilla_canales_tv.md` | Depende de la prueba; si el operador no soporta sus condiciones → MODIFICA con órdenes |
| 4 | **Parrilla de canales TV modificada / canales eliminados** | "canales eliminados", "parrilla", "televisión", "canales premium", "Claro TV", "DirecTV" | `deber_informacion.md` + `parrilla_canales_tv.md` | CONFIRMA si el plan es general (no caracterizado) |
| 5 | **Gestión de cobranza / casas de cobro / llamadas de cobro** | "casa de cobranza", "cobro coactivo", "llamadas de cobro", "PQR vigente y me cobran" | `procedencia_recursos_ley1341.md` | IMPROCEDENTE (la gestión de cobro no es acto recurrible) |
| 6 | **Reporte negativo en centrales de riesgo** | "DataCrédito", "CIFIN", "centrales de riesgo", "reporte negativo", "habeas data" | `procedencia_recursos_ley1341.md` + `traslado_habeas_data.md` | IMPROCEDENTE + TRASLADO a Habeas Data |
| 7 | **Cobros por equipos en comodato / devolución de equipos** | "comodato", "equipo", "decodificador no entregado", "no devolví el equipo" | `procedencia_recursos_ley1341.md` (si no hay facturación contestada) | Evaluar caso por caso |
| 8 | **Cancelación del servicio** | "cancelar", "terminación del contrato", "solicité la cancelación", "siguen cobrando después de cancelar" | `cancelacion.md` (validar en Fase 2) | Variable según prueba de la solicitud |
| 9 | **Cláusula de permanencia / penalización por terminación anticipada** | "permanencia", "penalización", "multa por cancelar", "cláusula", "subsidio del equipo" | `permanencia.md` (validar en Fase 2) | Variable; revisar acreditación del beneficio |
| 10 | **Portabilidad numérica móvil** | "portabilidad", "cambio de operador", "no me dejan portar", "porting rechazado" | `portabilidad.md` (validar en Fase 2) | CONFIRMA si rechazo es por causal válida; REVOCA si no |
| 11 | **Calidad del servicio (cortes, intermitencia, baja velocidad)** | "cortes", "no funciona", "intermitencia", "lento", "sin señal", "internet caído" | `calidad_servicio.md` (validar en Fase 2) | MODIFICA si hay indisponibilidad >7h sin compensar |

---

## Triggers ortogonales (siempre verificar, no excluyentes)

- **¿Hay otro expediente del mismo usuario en el sistema?** Aplicar **triple búsqueda** (manual SIC). Si sí → agregar numeral QUINTO con `acumulacion_expedientes.md`.
- **¿La controversia incluye centrales de riesgo?** → agregar `traslado_habeas_data.md` y ARTÍCULO de traslado en RESUELVE.
- **¿Faltan pruebas en el expediente?** → solicitar pruebas (ver punto 13 del manual SIC). Por defecto solo si el revisor lo aprueba.

---

## Tipologías no cubiertas aún (gap)

A medida que aparezcan en Fase 2 con casos reales, agregar bloques nuevos para:
- Calidad del servicio (cortes, intermitencia).
- Portabilidad numérica.
- Facturación errónea sin promoción de por medio.
- Cesión de contrato.
- Cláusula de permanencia.
- Roaming.

Cuando se identifique un nuevo tema, crear `bloques/<nombre>.md` y agregar fila a esta tabla.
