# k6-sqlserver-lab

Laboratorio de **pruebas de performance para SQL Server con k6** (extension
`xk6-sql`). Las pruebas se disparan desde **GitHub Actions** (automatico por cron
y manual), un **agente de IA** valida los resultados y se publica un **reporte
Markdown con graficas Mermaid**.

El laboratorio es **auto-contenido**: el workflow levanta SQL Server en un
contenedor, siembra un esquema de ejemplo y corre k6 contra el. No necesitas una
base de datos externa ni secrets.

## Infografia

Paso a paso del pipeline y division de la arquitectura por capas:

![Infografia — k6 x SQL Server Perf Lab](infografia.png)

> Fuente editable: [`infografia.html`](infografia.html). Para regenerar el PNG:
> `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --force-device-scale-factor=2 --screenshot=infografia.png --window-size=1200,2600 infografia.html`

---

## Ultimo reporte

<!-- LATEST_REPORT_START -->
**Ultima corrida:** 2026-08-10 14:35 UTC - Veredicto `WARN`  
Reporte completo: [`reports/report-2026-08-10_1435.md`](reports/report-2026-08-10_1435.md)

| Escenario | Queries | Error % | p95 (ms) | q/s |
| --- | --- | --- | --- | --- |
| load | 20060 | 0% | 268 | 333.5 |
| smoke | 7320 | 0% | 65 | 243.67 |
<!-- LATEST_REPORT_END -->

---

## Como funciona

```mermaid
flowchart LR
    A[Trigger<br/>cron o manual] --> B[SQL Server 2022<br/>contenedor]
    B --> C[Seed<br/>esquema + datos]
    C --> D[k6 + xk6-sql<br/>smoke / load]
    D --> E[Metricas por query<br/>p50/p95/p99, q/s, error]
    E --> F[Agente IA<br/>GitHub Models]
    F --> G[gen_report.py<br/>Markdown + Mermaid]
    G --> H[Reporte + README<br/>+ artefactos]
```

1. El workflow **levanta SQL Server 2022** en un contenedor Docker.
2. **Siembra** el esquema de ejemplo (`db/seed.sql`): tablas `customers`,
   `products`, `orders`, `order_items` con datos.
3. **k6** (binario construido con `xk6-sql` + driver de SQL Server) ejecuta un
   workload OLTP y mide la latencia de cada tipo de query.
4. Un **agente de IA** (GitHub Models, sin API key externa) analiza las metricas
   contra los SLOs y emite `PASS` / `WARN` / `FAIL` con recomendaciones. Si no
   esta disponible, hay un fallback por umbrales.
5. **`gen_report.py`** arma el reporte Markdown con graficas Mermaid y actualiza
   esta seccion del README.

---

## Workload (tipos de query)

| Query | Que ejercita |
| --- | --- |
| `point_select` | Lookup por PK (indice unico) |
| `range_scan` | Barrido por rango de fecha |
| `join` | JOIN de 3 tablas filtrado por ciudad |
| `aggregate` | `GROUP BY` + `SUM` sobre 60k renglones |
| `insert_update` | Camino de escritura (INSERT + UPDATE) |

---

## Ejecutar

### Manual (desde GitHub)
`Actions` -> `Performance SQL Server (k6)` -> `Run workflow`.

| Input | Descripcion | Default |
| --- | --- | --- |
| `scenario` | `both`, `smoke` o `load` | `both` |
| `vus` | usuarios virtuales | smoke 3 / load 20 |
| `duration` | duracion (ej. `45s`) | smoke 30s / load 60s |

### Automatico
Corre todos los dias a las **13:30 UTC** (~07:30 CDMX).

### Local (opcional)
```bash
# 1. binario de k6 con soporte SQL
go install go.k6.io/xk6/cmd/xk6@latest
xk6 build --with github.com/grafana/xk6-sql \
          --with github.com/grafana/xk6-sql-driver-sqlserver --output ./k6

# 2. SQL Server local + seed
docker run -d --name mssql -e ACCEPT_EULA=Y -e MSSQL_SA_PASSWORD=Perf_Lab_2024 \
  -p 1433:1433 mcr.microsoft.com/mssql/server:2022-latest
docker cp db/seed.sql mssql:/tmp/seed.sql
docker exec mssql /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa \
  -P Perf_Lab_2024 -C -i /tmp/seed.sql

# 3. correr
./k6 run scripts/db-perf.js -e SCENARIO=smoke -e VUS=3 -e DURATION=30s \
  -e CONN="sqlserver://sa:Perf_Lab_2024@localhost:1433?database=perflab&encrypt=disable"
python3 scripts/gen_report.py --out reports/report-local.md --date local \
  --metrics reports/metrics-smoke.json
```

---

## Estructura

```
k6-sqlserver-lab/
├── README.md
├── infografia.png              # infografia (imagen): paso a paso + arquitectura
├── infografia.html             # fuente editable de la infografia
├── .github/workflows/db-perf.yml
├── db/seed.sql                 # esquema + datos de ejemplo
├── scripts/
│   ├── db-perf.js              # prueba k6 (xk6-sql), escribe metricas JSON
│   └── gen_report.py           # metricas -> Markdown + Mermaid
└── reports/                    # reportes generados por corrida
```

---

## SLOs de referencia

| Metrica | PASS | WARN | FAIL |
| --- | --- | --- | --- |
| % de error | < 0.1% | 0.1% - 1% | > 1% |
| Latencia p95 (global) | < 200 ms | 200 - 400 ms | > 400 ms |

Ajustables en el paso *"Armar prompt para el agente"*, en el fallback del
workflow y en los `thresholds` de `scripts/db-perf.js`.

---

_Laboratorio auto-contenido con fines de aprendizaje/benchmark. La contrasena del
contenedor es efimera (solo vive durante la corrida en CI)._
