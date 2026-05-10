# Frases ancla literales por numeral

> **Estructura vigente (compacta):** TÍTULO + SEGUNDO + TERCERO + CUARTO. NO se usa PRIMERO, NO se usa RESUELVE separado. La decisión administrativa (CONFIRMA / MODIFICA / REVOCA / IMPROCEDENTE) va integrada al final del CUARTO.

Estas frases aparecen palabra por palabra en las resoluciones del despacho. Deben usarse **literales** salvo los placeholders entre llaves `{...}`.


---

## TÍTULO

Formato literal (terminado en punto):
> Decisión Empresarial: CUN {NUMERO_CUN} del {FECHA_PRIMERA_RESPUESTA}.

Ejemplos reales:
- "Decisión Empresarial: CUN 4488-25- 0000736103 del 25 de junio de 2025."
- "Decisión Empresarial: CUN 4488-25- 0000495929 del 15 de abril de 2025."
- "Decisión Empresarial: CUN 4331250000475900 del 26 de noviembre de 2025."

**Etiqueta de sentido opcional sobre el título** (observada en ~50 % de los casos firmados): una línea aparte, en mayúscula, con `CONFIRMA`, `REVOCA`, `MODIFICA` o `IMPROCEDENTE`. Debe coincidir con el sentido del fallo.

Ejemplo:
> CONFIRMA
>
> Decisión Empresarial: CUN 4488-25- 0000354768 del 20 de marzo de 2025.

---

## SEGUNDO (inconformidad del usuario)

Frase ancla de apertura — **usar literal**:
> SEGUNDO: Que, de acuerdo con la información allegada al expediente, se advierte que el motivo de inconformidad expuesto por el usuario titular de {la línea / la cuenta fija / la línea móvil} No. {NUMERO}, se circunscribe a que {HECHOS_DEL_USUARIO}.

Variantes válidas observadas:
- "...usuario titular de la cuenta fija No. 9466904, se circunscribe a que..."
- "...usuario titular de la línea xxxxx, se circunscribe a que..."
- Para empresas: "...usuario titular de la linea {NUMERO}, se circunscribe a que la empresa {RAZON_SOCIAL} había sido titular..."

Después del párrafo de hechos, suelen seguir 1-3 párrafos más con: solicitud del usuario, derechos invocados, y resumen del recurso de reposición/apelación.

---

## TERCERO (posición del operador)

Frase ancla de apertura — **usar literal**:
> TERCERO: Que, frente a la inconformidad expuesta por el usuario, el operador manifestó que, {POSICION_DEL_OPERADOR}.

Después se enumeran (a menudo con A./B./C. o numerales) los argumentos y pruebas que el operador aportó.

---

## CUARTO (consideraciones de la SIC – con subsecciones del manual)

Frase ancla de apertura (intro) — **usar literal**:
> CUARTO: Que, en virtud de los hechos expuestos, entra esta Dirección a hacer las siguientes consideraciones:

El CUARTO **siempre se divide en subsecciones numeradas** `4.1`, `4.2`, `4.3`... — una por cada pretensión / tipología detectada. Aunque solo haya un tema, se abre con `4.1`.

Cada subsección sigue este orden:
1. **Título** corto del tema (negrita).
2. Frase introductoria: *"Observa la Dirección que el usuario presenta un desacuerdo..."* o *"En el presente caso, frente a la inconformidad del usuario, resulta pertinente mencionar..."* o *"Sea lo primero advertir que la petición presentada..."* (en improcedencias).
3. Cita literal del artículo entre comillas (en itálica con sangría) + `(Destacado fuera de texto)` cuando aplique.
4. Interpretación: *"De acuerdo con lo expuesto..."* / *"De lo anterior se colige que..."* / *"De lo citado se colige que..."*.
5. Aplicación al caso concreto con citas a `consecutivo – X, página Y, folio Z` y `desde el minuto MM:SS`.
6. Cierre estándar (ver más abajo).

**Sin tope de palabras.** El CUARTO puede ocupar varios párrafos por subsección.

---

## Cierres de cada subsección 4.x

### Cierre CONFIRMA (cuando el operador cumplió):
> De este modo, se puede concluir que el operador cumplió con sus obligaciones en relación al {TEMA} de manera clara, cierta, completa, oportuna y gratuita al usuario de sus servicios y, en consecuencia; se confirmará la decisión del operador, en este punto.

### Cierre REVOCA/MODIFICA (cuando el operador incumplió):
> De este modo, considera esta Dirección que el operador incumplió con sus obligaciones en relación al {TEMA} de manera clara, cierta, completa, oportuna y gratuita y que no induzca error a los suscriptores o usuarios de sus servicios, en forma previa y en todo momento durante la ejecución del contrato; razón por la cual se ordena al operador: (i) {ORDEN_1}; y, (ii) {ORDEN_2}.

Seguido de:
> En ningún caso, habrá lugar al ajuste a la facturación sobre cuentas futuras. Sólo podrá hacerse cruce de cuentas en el evento en el que el usuario se encuentre en mora en el pago de obligaciones que no hayan sido objeto de pronunciamiento en la presente decisión y hasta por el monto de lo adeudado.

### Cierre IMPROCEDENTE (cuando la pretensión no está dentro del art. 54 Ley 1341/2009):
> Corolario de lo expuesto, esta Dirección declarará improcedente la pretensión presentada de manera subsidiaria por el usuario bajo este numeral.

---

## Citación de pruebas

### Pruebas documentales en el expediente:
> consecutivo – {N}, página {X}, folio {Y} al {ZZ} del radicado {XX-XXXX}

Ejemplos reales:
- "en consecutivo – 0, página 5"
- "en consecutivo – 0, página 2, folio 20 del expediente"
- "en consecutivo – 0, página 3, (Exp. 25 – 202728)"

### Imagen como prueba:
> Imagen N: {Descripción}.
> Fuente: {Tipo de documento}. Consecutivo {N}. Página {X}. Radicado {XX-XXXX}

### Audio (contrato magnetofónico, llamada grabada):
> en consecutivo – {N}, página {X} donde constan las condiciones... desde el minuto {MM:SS}

Ejemplos reales:
- "en el minuto 04:25 se cuenta con la aceptación..."
- "desde el minuto 4:19, un paquete de servicios que incluye..."
- "entre los minutos 4:25 y 4:42"
- "desde el minuto 10:45 televisión digital Plus..."

**Importante:** los timestamps deben tomarse de la transcripción de Whisper (formato `[HH:MM:SS]`).

---

## QUINTO (cuando aplica acumulación de expedientes)

Ver `bloques/acumulacion_expedientes.md` — se incluye literal cuando hay otro expediente del mismo usuario radicado y se acumula de oficio.

---

## ARTÍCULO X (cuando aplica traslado a otra dependencia)

Ejemplos:
> ARTÍCULO X: Trasladar copia de la solicitud de {OBJETO}, así como del presente acto administrativo, a la {DEPENDENCIA}, por lo expuesto en la parte motiva de la presente Resolución.

Ver `bloques/traslado_habeas_data.md` para el caso de centrales de riesgo.

---

## RESUELVE (parte resolutiva)

Conectores estándar:
- "ARTÍCULO PRIMERO: CONFIRMAR la decisión empresarial CUN {N} del {FECHA}, expedida por {OPERADOR}, por las razones expuestas en la parte motiva del presente acto administrativo."
- "ARTÍCULO PRIMERO: MODIFICAR la decisión empresarial CUN {N} del {FECHA}, expedida por {OPERADOR}, en el sentido de {EXPLICACION_BREVE}, por las razones expuestas en la parte motiva del presente acto administrativo."
- "ARTÍCULO PRIMERO: REVOCAR la decisión empresarial CUN {N} del {FECHA}, expedida por {OPERADOR}, por las razones expuestas en la parte motiva del presente acto administrativo."
- "ARTÍCULO PRIMERO: DECLARAR IMPROCEDENTE el recurso de apelación presentado por {USUARIO} contra la decisión empresarial CUN {N}, por las razones expuestas en la parte motiva del presente acto administrativo."

Verificar el formato exacto en `manual_sic.docx` antes de escribir.
