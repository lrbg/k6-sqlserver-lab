// Prueba de performance de SQL Server con k6 + xk6-sql.
// Requiere un binario de k6 construido con:
//   xk6 build --with github.com/grafana/xk6-sql --with github.com/grafana/xk6-sql-driver-sqlserver
//
// Variables de entorno:
//   CONN      cadena de conexion sqlserver://...
//   SCENARIO  nombre del escenario (smoke|load) -> nombre del archivo de metricas
//   VUS       usuarios virtuales
//   DURATION  duracion (ej. 30s)
import sql from "k6/x/sql";
import driver from "k6/x/sql/driver/sqlserver";
import { Trend, Counter } from "k6/metrics";

const CONN = __ENV.CONN ||
  "sqlserver://sa:Perf_Lab_2024@localhost:1433?database=perflab&encrypt=disable";
const SCENARIO = __ENV.SCENARIO || "smoke";

const db = sql.open(driver, CONN);

// Tipos de query que representan un workload OLTP tipico
const QUERIES = ["point_select", "range_scan", "join", "aggregate", "insert_update"];

const lat = {}, cnt = {}, err = {};
for (const q of QUERIES) {
  lat[q] = new Trend(`q_${q}`, true);
  cnt[q] = new Counter(`n_${q}`);
  err[q] = new Counter(`e_${q}`);
}
const latAll = new Trend("q_all", true);
const nAll = new Counter("n_all");
const eAll = new Counter("e_all");

export const options = {
  vus: Number(__ENV.VUS || 3),
  duration: __ENV.DURATION || "30s",
  summaryTrendStats: ["avg", "min", "med", "max", "p(90)", "p(95)", "p(99)"],
  thresholds: {
    // SLOs de referencia (informativos; el veredicto final lo da el agente)
    "q_all": ["p(95)<200"],
    "e_all": ["count<1"],
  },
};

const CITIES = ["CDMX", "GDL", "MTY", "PUE", "QRO"];
function rnd(n) { return 1 + Math.floor(Math.random() * n); }
function pick(a) { return a[Math.floor(Math.random() * a.length)]; }

function run(name, fn) {
  const t0 = Date.now();
  try {
    fn();
  } catch (e) {
    err[name].add(1); eAll.add(1);
  }
  const d = Date.now() - t0;
  lat[name].add(d); latAll.add(d);
  cnt[name].add(1); nAll.add(1);
}

export default function () {
  run("point_select", () =>
    db.query(`SELECT id, name, city FROM customers WHERE id = ${rnd(5000)}`));

  run("range_scan", () =>
    db.query(`SELECT COUNT(*) c FROM orders WHERE order_date > DATEADD(day, -7, SYSDATETIME())`));

  run("join", () =>
    db.query(
      `SELECT TOP 50 o.id, c.name, oi.qty
       FROM orders o
       JOIN customers c   ON c.id = o.customer_id
       JOIN order_items oi ON oi.order_id = o.id
       WHERE c.city = '${pick(CITIES)}'`));

  run("aggregate", () =>
    db.query(
      `SELECT p.category, SUM(oi.qty * oi.price) rev
       FROM order_items oi
       JOIN products p ON p.id = oi.product_id
       GROUP BY p.category`));

  run("insert_update", () => {
    const id = 1000000 + rnd(9000000);
    db.exec(`INSERT INTO orders (id, customer_id, order_date, total) VALUES (${id}, ${rnd(5000)}, SYSDATETIME(), 0)`);
    db.exec(`UPDATE orders SET total = ${rnd(1000)} WHERE id = ${id}`);
  });
}

export function teardown() {
  db.close();
}

export function handleSummary(data) {
  const dur = ((data.state && data.state.testRunDurationMs) || 1000) / 1000;

  const vals = (name) => ((data.metrics[name] || {}).values || {});
  const r1 = (x) => Math.round((x || 0) * 10) / 10;

  function block(latName, nName, eName) {
    const v = vals(latName);
    const n = vals(nName).count || 0;
    const e = vals(eName).count || 0;
    return {
      samples: n,
      errors: e,
      error_pct: n ? Math.round((e / n) * 10000) / 100 : 0,
      avg_ms: r1(v.avg),
      min_ms: Math.round(v.min || 0),
      max_ms: Math.round(v.max || 0),
      p50_ms: r1(v.med),
      p90_ms: r1(v["p(90)"]),
      p95_ms: r1(v["p(95)"]),
      p99_ms: r1(v["p(99)"]),
      throughput_rps: Math.round((n / dur) * 100) / 100,
      duration_s: r1(dur),
    };
  }

  const by = {};
  for (const q of QUERIES) by[q] = block(`q_${q}`, `n_${q}`, `e_${q}`);

  const out = {
    scenario: SCENARIO,
    overall: block("q_all", "n_all", "e_all"),
    by_endpoint: by, // "endpoint" = tipo de query (compatible con gen_report.py)
    empty: (vals("n_all").count || 0) === 0,
  };

  const path = `reports/metrics-${SCENARIO}.json`;
  const res = {};
  res[path] = JSON.stringify(out, null, 2);
  res["stdout"] =
    `\n[${SCENARIO}] queries=${out.overall.samples} err=${out.overall.error_pct}% ` +
    `p95=${out.overall.p95_ms}ms throughput=${out.overall.throughput_rps}/s\n`;
  return res;
}
