#!/usr/bin/env python3
"""Genera un reporte Markdown con graficas Mermaid a partir de metricas de k6 (SQL Server).

Uso:
    python scripts/gen_report.py --out reports/report-XXX.md --date "..." \
        --run-url "https://..." [--verdict verdict.md] --metrics reports/metrics-*.json

Actualiza la seccion "ultimo reporte" del README entre los marcadores
<!-- LATEST_REPORT_START --> y <!-- LATEST_REPORT_END -->.

Las metricas usan la clave "by_endpoint" que aqui representa el TIPO DE QUERY.
"""
import argparse
import json
import os


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def mermaid_bar(title, y_label, labels, values):
    xs = ", ".join(f'"{l}"' for l in labels)
    ys = ", ".join(str(v) for v in values)
    return (
        "```mermaid\n"
        "xychart-beta\n"
        f'    title "{title}"\n'
        f"    x-axis [{xs}]\n"
        f'    y-axis "{y_label}"\n'
        f"    bar [{ys}]\n"
        "```\n"
    )


def compute_badge(metrics, warn_err=0.1, fail_err=1.0, warn_p95=200, fail_p95=400):
    """Veredicto DETERMINISTA desde las metricas vs SLOs (no depende del texto del agente).

    Toma el peor error% y el peor p95 global entre los escenarios.
    """
    worst_err = 0.0
    worst_p95 = 0.0
    seen = False
    for m in metrics:
        o = m.get("overall") or {}
        if not o:
            continue
        seen = True
        worst_err = max(worst_err, o.get("error_pct", 0) or 0)
        worst_p95 = max(worst_p95, o.get("p95_ms", 0) or 0)
    if not seen:
        return "N/D"
    if worst_err > fail_err or worst_p95 > fail_p95:
        return "FAIL"
    if worst_err > warn_err or worst_p95 > warn_p95:
        return "WARN"
    return "PASS"


def scenario_section(m):
    scenario = m.get("scenario", "?")
    if m.get("empty"):
        return f"### Escenario: `{scenario}`\n\n> No se registraron queries en esta corrida.\n"

    o = m["overall"]
    queries = m["by_endpoint"]
    labels = list(queries.keys())

    lines = [f"### Escenario: `{scenario}`\n"]
    lines.append("| Metrica | Valor |")
    lines.append("| --- | --- |")
    lines.append(f"| Queries ejecutadas | {o['samples']} |")
    lines.append(f"| Errores | {o['errors']} ({o['error_pct']}%) |")
    lines.append(f"| Latencia media | {o['avg_ms']} ms |")
    lines.append(f"| p50 / p90 / p95 / p99 | {o['p50_ms']} / {o['p90_ms']} / {o['p95_ms']} / {o['p99_ms']} ms |")
    lines.append(f"| Min / Max | {o['min_ms']} / {o['max_ms']} ms |")
    lines.append(f"| Throughput | {o['throughput_rps']} queries/s |")
    lines.append(f"| Duracion | {o['duration_s']} s |")
    lines.append("")

    lines.append(mermaid_bar(
        f"Latencia por percentil - {scenario} (ms)", "ms",
        ["p50", "p90", "p95", "p99", "max"],
        [o["p50_ms"], o["p90_ms"], o["p95_ms"], o["p99_ms"], o["max_ms"]],
    ))
    lines.append("")

    lines.append(mermaid_bar(
        f"Latencia p95 por query - {scenario} (ms)", "ms",
        labels, [queries[l]["p95_ms"] for l in labels],
    ))
    lines.append("")

    lines.append(mermaid_bar(
        f"Throughput por query - {scenario} (queries/s)", "queries/s",
        labels, [queries[l]["throughput_rps"] for l in labels],
    ))
    lines.append("")

    lines.append(mermaid_bar(
        f"Errores por query - {scenario} (%)", "%",
        labels, [queries[l]["error_pct"] for l in labels],
    ))
    lines.append("")

    lines.append("<details><summary>Detalle por query</summary>\n")
    lines.append("| Query | Ejecuciones | Error % | avg | p95 | p99 | q/s |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for l in labels:
        e = queries[l]
        lines.append(f"| {l} | {e['samples']} | {e['error_pct']}% | {e['avg_ms']} | {e['p95_ms']} | {e['p99_ms']} | {e['throughput_rps']} |")
    lines.append("\n</details>\n")

    return "\n".join(lines)


def update_readme(readme_path, summary_block):
    start = "<!-- LATEST_REPORT_START -->"
    end = "<!-- LATEST_REPORT_END -->"
    if not os.path.exists(readme_path):
        return
    with open(readme_path, encoding="utf-8") as fh:
        content = fh.read()
    if start not in content or end not in content:
        return
    pre = content.split(start)[0]
    post = content.split(end)[1]
    new = f"{pre}{start}\n{summary_block}\n{end}{post}"
    with open(readme_path, "w", encoding="utf-8") as fh:
        fh.write(new)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--run-url", default="")
    ap.add_argument("--verdict", default="")
    ap.add_argument("--metrics", nargs="+", required=True)
    ap.add_argument("--readme", default="README.md")
    args = ap.parse_args()

    metrics = [load(p) for p in args.metrics if os.path.exists(p)]

    verdict_text = ""
    if args.verdict and os.path.exists(args.verdict):
        with open(args.verdict, encoding="utf-8") as fh:
            verdict_text = fh.read().strip()
    # Badge determinista desde metricas vs SLOs (autoritativo).
    badge = compute_badge(metrics)

    doc = ["# Reporte de performance - SQL Server (k6)\n"]
    doc.append(f"**Fecha:** {args.date}  ")
    doc.append(f"**Veredicto (SLO):** `{badge}`  ")
    if args.run_url:
        doc.append(f"**Corrida:** [ver en GitHub Actions]({args.run_url})  ")
    doc.append("")

    doc.append("## Analisis del agente de IA\n")
    doc.append(verdict_text if verdict_text else "_El agente no devolvio analisis en esta corrida._")
    doc.append("")

    doc.append("## Resultados\n")
    for m in metrics:
        doc.append(scenario_section(m))
        doc.append("")

    report_md = "\n".join(doc)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(report_md)

    summary_lines = [
        f"**Ultima corrida:** {args.date} - Veredicto `{badge}`  ",
        f"Reporte completo: [`{args.out}`]({args.out})",
        "",
        "| Escenario | Queries | Error % | p95 (ms) | q/s |",
        "| --- | --- | --- | --- | --- |",
    ]
    for m in metrics:
        if m.get("empty"):
            summary_lines.append(f"| {m.get('scenario','?')} | 0 | - | - | - |")
            continue
        o = m["overall"]
        summary_lines.append(
            f"| {m['scenario']} | {o['samples']} | {o['error_pct']}% | {o['p95_ms']} | {o['throughput_rps']} |"
        )
    update_readme(args.readme, "\n".join(summary_lines))

    print(f"Reporte generado: {args.out}")


if __name__ == "__main__":
    main()
