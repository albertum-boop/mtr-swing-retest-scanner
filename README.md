# MTR Multitemporal Swing Retest

Aplicación diaria del método congelado **MTR Multitemporal v1.2**. El motor conserva
íntegramente la rama mensual MTR Swing Retest v1.0 y añade dos ramas independientes:
LM2, formada en la penúltima sesión NYSE del mes, y la rama semanal incremental.
Las señales operativas son:

- todas las señales mensuales A+, A y B;
- únicamente las señales LM2 A+ y A;
- únicamente las señales semanales A+ y A;
- una sola señal con distintivo de confluencia cuando varios marcos confirman el mismo
  ticker en la misma fecha de evento.

Las B LM2 y semanales se calculan para auditar los filtros, pero no se publican como entrada
ni generan correo. Un cooldown común de diez sesiones evita dos entradas próximas en el
mismo ticker, aunque el segundo evento se conserva marcado para auditoría. La aplicación no
envía órdenes. `R5`, `R10`, `MFE` y `MAE` describen el recorrido posterior y no constituyen
una regla automática de salida.

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

## Formación LM2

LM2 se forma en la **penúltima sesión NYSE de cada mes natural**. No sustituye el cierre
mensual: abre un ciclo adicional con su propio nivel, ATR y candidatos congelados. Si el
mes termina un lunes, por ejemplo, LM2 se forma el viernes anterior; el calendario se calcula
con sesiones reales y festivos de NYSE, no restando un día natural.

LM2 usa la misma selección D10 + top 20% de SwingScore y el mismo retest que las demás ramas.
El grado operativo, sin embargo, se calcula con tres condiciones observables al cierre LM2:

```text
gap_formación = Apertura_ajustada(t) / Cierre_ajustado(t-1) - 1

Q_LM2 = 1[gap_formación >= 0]
      + 1[percentil_ATR20_D10 >= 0,85]
      + 1[SMA200(t) / SMA200(t-20) - 1 >= 0,075]
```

- **A+**: 3 puntos;
- **A**: 2 puntos;
- **B**: 0 o 1 punto; se conserva en `reference/lm2_signals_v1_0.csv`, pero no es entrada.

Los umbrales se aplican sin redondear. El gap y la pendiente usan precios ajustados; el
percentil ATR se calcula transversalmente dentro de D10 en esa formación.

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

Las tres ramas usan exactamente el mismo patrón:

1. nivel `L`: cierre ajustado de formación;
2. expansión: máximo ajustado ≥ `L + 0,25 × ATR20`;
3. retest: primer contacto con `[L − 0,25 ATR, L + 0,25 ATR]` en los días 2–5;
4. el contacto debe cerrar sobre `L`, en el 70% superior de su rango, no superar
   `L + 0,75 ATR` y negociar menos del 80% del volumen medio previo de 20 sesiones;
5. la entrada de referencia es la apertura ajustada de la sesión siguiente.

El **primer contacto** es definitivo. Si toca la banda y falla una condición, el ciclo se
rechaza; un contacto posterior no puede reactivarlo. Si no hay expansión o contacto antes
del final del día 5, la ventana expira.

## Unión, confluencia y cooldown

Las ramas se calculan independientemente y después se unen por `(ticker, event_date)`. Una
coincidencia conserva todos los grados, fechas de formación e identificadores de origen.
El grado maestro es el mejor grado realmente obtenido; la confluencia es un distintivo y no
produce una mejora automática.

Los identificadores mensuales existentes se preservan para no reenviar alertas históricas.
Una señal exclusivamente LM2 usa `MTR-LM2-v1.0:TICKER:FECHA`; una exclusivamente semanal
usa `MTR-Weekly-Cross-v1.0:TICKER:FECHA`.

Después de unir coincidencias exactas se aplica el cooldown por ticker. La primera señal
accionable bloquea las señales posteriores durante diez sesiones NYSE. Una señal suprimida:

- permanece en el histórico con `actionable=false`;
- registra `suppressed_by_cooldown` y la distancia en sesiones;
- no prolonga el cooldown;
- no genera correo ni una segunda entrada.

## Evidencia congelada 2019–2026

La referencia v1.2 contiene 322 eventos únicos:

| Componente | Señales |
|---|---:|
| Mensuales originales | 154 |
| Semanales A+/A | 91 |
| LM2 totales auditadas | 128 |
| LM2 A+/A | 92 |
| LM2 realmente incrementales | 90 |
| Coincidencias exactas semanal + LM2 | 2 |
| Unión única | 322 |

La unión queda distribuida en 108 A+, 189 A y 25 B. Las 38 B semanales permanecen en
`reference/weekly_signals_v1_0.csv` y las 36 B LM2 en `reference/lm2_signals_v1_0.csv`
como controles de auditoría. `reference/multitemporal_signals_v1_2.csv` contiene la unión
completa ordenada por calidad y fecha. Las referencias v1.0 mensual y v1.1 multitemporal
se mantienen sin modificación.

El perfil aislado LM2 que justificó el filtro es:

| Grado LM2 | n | R5 | MFE5 | MAE5 | R10 | MFE10 | MAE10 |
|---|---:|---:|---:|---:|---:|---:|---:|
| A+ | 33 | 8,02% | 16,59% | −6,26% | 15,07% | 26,49% | −8,32% |
| A | 59 | 3,10% | 10,56% | −6,66% | 3,90% | 17,31% | −9,87% |
| B | 36 | 1,15% | 6,94% | −6,47% | −1,79% | 9,64% | −9,92% |

Son medias por señal, no una curva de capital ni una promesa de rentabilidad. La entrada de
medición es la apertura siguiente al retest y cada horizonte contiene exactamente cinco o
diez sesiones posteriores.

## Monitor operativo

`public/data/current.json` publica simultáneamente la formación mensual, LM2 si su ventana
sigue activa y las formaciones semanales activas. Cada candidato lleva un `candidate_id`
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

El correo incluye grado y marco temporal. Solo se envían señales accionables confirmadas en
la sesión de corte, nunca señales atrasadas, B LM2/semanales ni eventos suprimidos por
cooldown. Un identificador se registra como
enviado únicamente después de un envío SMTP correcto.

## Automatización y despliegue

`.github/workflows/daily-scan.yml` se ejecuta de lunes a viernes a las 23:30 UTC. Descarga
el universo una sola vez cuando necesita congelar una formación, actualiza los ciclos activos,
envía alertas y versiona:

- `state/formations/` para formaciones mensuales;
- `state/lm2_formations/` para la penúltima sesión mensual;
- `state/weekly_formations/` para cierres semanales y su conjunto seleccionado completo;
- `public/data/current.json` y `public/data/history.json`;
- el registro de alertas y el resultado de la última ejecución.

`vercel.json` declara `public/` como salida estática. Cada commit de datos despliega la web
sin servidor ni base de datos adicional.

## Contrato de reproducción

Las pruebas impiden cambiar silenciosamente los conteos históricos, el orden calidad-fecha,
las ecuaciones mensuales y LM2, el cruce semanal, los filtros B, la unión por evento o el
cooldown. Cualquier cambio de umbral debe usar una versión distinta del método.
