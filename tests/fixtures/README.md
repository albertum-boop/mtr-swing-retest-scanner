# Cierres de ALM y HUT para la regresión de octubre de 2026

`october_2026_trend_closes.csv` contiene 240 cierres por ticker, hasta el cierre del evento
2026-10-05. Los cierres hasta 2026-09-25 proceden del archivo OHLCV original `prices.zip`
utilizado para la referencia. Los seis cierres posteriores se contrastaron con las tablas
históricas de StockAnalysis (fuente indicada por el sitio: S&P Global Market Intelligence):

- https://stockanalysis.com/stocks/alm/history/
- https://stockanalysis.com/stocks/hut/history/

Los valores exactos del evento se conservan desde los registros del escáner. La fixture
no contiene precios posteriores al evento y solo se utiliza para comprobar el bloqueo de
la tendencia. Las barras OHLCV de octubre usadas en la prueba de retest proceden del
registro histórico inspeccionado; las barras antiguas sintéticas de esa prueba no se usan
para medir rentabilidad. La evaluación de los 323 eventos usa el archivo original completo,
no esta fixture.
