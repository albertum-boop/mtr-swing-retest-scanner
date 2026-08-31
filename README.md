# MTR Multitemporal Swing Retest

Aplicación diaria del método congelado **MTR Multitemporal v1.1**. El motor conserva
íntegramente la rama mensual MTR Swing Retest v1.0 y añade una rama semanal incremental.
Las señales operativas son:

- todas las señales mensuales A+, A y B;
- únicamente las señales semanales A+ y A;
- una sola señal con distintivo de confluencia cuando ambos marcos confirman el mismo
  ticker en la misma fecha de evento.

Las B semanales se calculan para poder auditar el filtro, pero no se publican, no se añaden
al histórico operativo y no generan correo. La aplicación no envía órdenes. `R5`, `R10`,
`MFE` y `MAE` describen el recorrido posterior y no constituyen una regla automática de salida.

## Base matemática común

En cada fecha de formación (t), el universo exige precio de cierre sin ajustar de al menos
5 USD y volumen monetario medio de 20 sesiones (`ADV20`) de al menos 10 M USD. El momentum es:

```text
MOM12-1(t) = P_ajustada(t-21) / P_ajustada(t-252) - 1
```

Se conserva el decil superior transversal, es decir, percentil de momentum estrictamente
superior a 0,90. Dentro de D10 se calculan percentiles transversales de:

- ATR20 como proporción del precio;
- MOM12-1;
- correlación de 20 sesiones entre retorno y log-volumen.

El `SwingScore` es la media simple de esos tres percentiles. Se conserva el 20% superior
del score, usando un corte estricto superior a 0,80.

## Formación mensual

La rama mensual se congela en la última sesión bursátil de cada mes. Durante las cinco
sesiones siguientes sigue los candidatos sin recalcular sus niveles. Conserva la clasificación
histórica A+, A y B de MTR Swing Retest v1.0.

## Formación semanal incremental

La rama semanal se congela en la última sesión NYSE de cada semana. Una acción solo abre
un ciclo semanal si está seleccionada ahora y no estaba seleccionada en el cierre semanal
anterior:

```text
cruce_semanal(t) = seleccionada(t) AND NOT seleccionada(t-1 semana)
```

Salir de la selección durante al menos un cierre semanal rearma el ticker. Esto evita emitir
la misma candidatura cada semana mientras permanece dentro del top 20%.

El grado semanal se obtiene con cuatro puntos de calidad:

1. percentil de momentum dentro de D10 ≥ 0,75;
2. percentil de ATR dentro de D10 ≤ 0,85;
3. percentil final del SwingScore ≥ 0,86;
4. cierre del retest no más de 0,45 ATR sobre el nivel de formación.

La confirmación de volumen en formación exige `media_volumen_5 / media_volumen_20 - 1 ≥ 0`.
La clasificación congelada es:

- **A+**: al menos 3 puntos y confirmación de volumen;
- **A**: exactamente 2 puntos, o al menos 3 sin confirmación de volumen;
- **B**: 0 o 1 punto; queda descartada operacionalmente.

## Expansión y retest

Ambas ramas usan exactamente el mismo patrón:

1. nivel `L`: cierre ajustado de formación;
2. expansión: máximo ajustado ≥ `L + 0,25 × ATR20`;
3. retest: primer contacto con `[L − 0,25 ATR, L + 0,25 ATR]` en los días 2–5;
4. el contacto debe cerrar sobre `L`, en el 70% superior de su rango, no superar
   `L + 0,75 ATR` y negociar menos del 80% del volumen medio previo de 20 sesiones;
5. la entrada de referencia es la apertura ajustada de la sesión siguiente.

El **primer contacto** es definitivo. Si toca la banda y falla una condición, el ciclo se
rechaza; un contacto posterior no puede reactivarlo. Si no hay expansión o contacto antes
del final del día 5, la ventana expira.

## Unión y confluencia

Las ramas se calculan independientemente y después se unen por `(ticker, event_date)`. Una
coincidencia conserva los dos grados, las dos fechas de formación y los dos identificadores.
El grado maestro es el mejor grado realmente obtenido; la confluencia es un distintivo y no
produce una mejora automática.

Los identificadores mensuales existentes se preservan para no reenviar alertas históricas.
Una señal exclusivamente semanal usa `MTR-Weekly-Cross-v1.0:TICKER:FECHA`.

## Evidencia congelada 2019–2026

La referencia contiene 232 eventos únicos:

| Componente | Señales |
|---|---:|
| Mensuales originales | 154 |
| Semanales A+/A | 91 |
| Coincidencias exactas | 13 |
| Semanales realmente incrementales | 78 |
| Unión única | 232 |

La unión queda distribuida en 75 A+, 132 A y 25 B. Las 38 B semanales permanecen en
`reference/weekly_signals_v1_0.csv` únicamente como control de auditoría. El archivo
`reference/multitemporal_signals_v1_1.csv` contiene la unión completa ordenada por calidad
y fecha. El original mensual sigue en `reference/signals_v1_0.csv`.

## Monitor operativo

`public/data/current.json` publica simultáneamente la formación mensual y las formaciones
semanales cuya ventana de cinco sesiones sigue activa. Cada candidato lleva un `candidate_id`
único, su marco, fecha de formación, niveles congelados, última sesión evaluada y estado.

Una señal confirmada en la sesión de corte es accionable para la **próxima apertura**. Las
señales anteriores de los ciclos activos permanecen visibles como referencia, sin presentarse
como entradas nuevas.

## Ejecución local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
python -m pytest
python -m mtr_scanner
```

Para auditar una fecha con datos OHLCV locales:

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
| `ALERT_TO` | destinatarios separados por coma |

El correo incluye grado y marco temporal. Solo se envían señales confirmadas en la sesión
de corte, nunca señales atrasadas de una reconstrucción. Un identificador se registra como
enviado únicamente después de un envío SMTP correcto.

## Automatización y despliegue

`.github/workflows/daily-scan.yml` se ejecuta de lunes a viernes a las 23:30 UTC. Descarga
el universo una sola vez cuando necesita congelar una formación, actualiza los ciclos activos,
envía alertas y versiona:

- `state/formations/` para formaciones mensuales;
- `state/weekly_formations/` para cierres semanales y su conjunto seleccionado completo;
- `public/data/current.json` y `public/data/history.json`;
- el registro de alertas y el resultado de la última ejecución.

`vercel.json` declara `public/` como salida estática. Cada commit de datos despliega la web
sin servidor ni base de datos adicional.

## Contrato de reproducción

Las pruebas impiden cambiar silenciosamente los conteos históricos, el orden calidad-fecha,
las ecuaciones mensuales, el cruce semanal, el filtro que excluye B semanal o la unión por
evento. Cualquier cambio de umbral debe usar una versión distinta del método.
