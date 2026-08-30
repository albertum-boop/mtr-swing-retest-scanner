# MTR Swing Retest Scanner

Aplicación diaria del método congelado **MTR Swing Retest v1.0**. El motor selecciona
acciones por momentum transversal, aplica el SwingScore, espera una secuencia de expansión
y retest y publica señales mutuamente excluyentes **A+**, **A** o **B**.

La aplicación no envía órdenes ni incluye todavía una regla operativa de salida. `R5`, `R10`,
`MFE` y `MAE` son métricas de validación del recorrido posterior.

## Arquitectura

1. Al cierre mensual se descarga aproximadamente año y medio de datos del universo.
2. Se aplica precio ≥ 5 USD y ADV20 ≥ 10 M USD.
3. Se calcula `MOM12-1 = P(t-21)/P(t-252)-1` y se conserva D10.
4. Dentro de D10 se calcula el SwingScore y se conserva su top 20%.
5. Durante las cinco sesiones siguientes solo se actualizan esos candidatos.
6. Se evalúa el primer contacto con la banda después de la expansión. Si falla una condición,
   el candidato queda descartado y un contacto posterior no puede reactivarlo.
7. Una señal nueva se guarda en JSON, aparece en la web y puede enviarse por SMTP.

Los precios completos no se versionan. La formación mensual contiene únicamente los 25–40
candidatos necesarios para el seguimiento diario.

## Ejecución local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest
python -m mtr_scanner
```

Para auditar una fecha con un directorio OHLCV local:

```bash
python -m mtr_scanner --as-of 2026-08-27 --prices-dir /ruta/a/prices
```

Cada CSV debe contener `Date, Open, High, Low, Close, Adj Close, Volume`.

## Alertas por correo

El workflow reconoce estos secretos de GitHub:

| Secreto | Ejemplo |
|---|---|
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `465` |
| `SMTP_USERNAME` | cuenta SMTP |
| `SMTP_PASSWORD` | contraseña de aplicación |
| `ALERT_FROM` | remitente |
| `ALERT_TO` | uno o varios destinatarios separados por coma |

Si faltan secretos, el escáner actualiza la web y registra `not_configured`, pero no marca las
señales como enviadas. Una señal solo entra en `state/sent_signals.json` después de un envío real.
El correo se limita a señales cuyo retest se confirmó en la sesión de corte: una primera instalación
o una reconstrucción histórica no envía alertas atrasadas. La web sí conserva todo el ciclo activo.

## Automatización

`.github/workflows/daily-scan.yml` se ejecuta de lunes a viernes a las 23:30 UTC, después de
las 18:00 de Nueva York tanto en horario de verano como de invierno. También admite ejecución
manual y una fecha de corte opcional.

El workflow versiona únicamente:

- la formación mensual;
- las señales actuales e históricas;
- el registro de alertas enviadas;
- el resultado de la última ejecución.

## Despliegue

Conectar el repositorio a Vercel. `vercel.json` declara `public/` como salida estática. Cada commit
de datos provoca un despliegue nuevo sin servidor ni base de datos adicional.

## Contrato de reproducción

`reference/signals_v1_0.csv` contiene las 154 señales auditadas: 49 A+, 79 A y 26 B. Las pruebas
impiden publicar una versión que cambie estos conteos, el orden calidad-fecha o las reglas de
clasificación. Cualquier cambio de parámetro debe usar otro `method_version`.

La reproducción histórica también congela una precisión operativa que no debe reinterpretarse:
**retest** significa el primer contacto con la banda tras la expansión. Exigir la primera vela que
cumpla simultáneamente todo y permitir contactos anteriores fallidos produciría una muestra distinta.
