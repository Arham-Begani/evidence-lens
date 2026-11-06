"""Self-contained, escaped HTML reports with unavoidable result provenance."""
from html import escape

from .io import write_new


def render_report(result, output):
    fixture = result["kind"] == "engineering_fixture"
    headline = "Engineering fixture — no model results" if fixture else "Reviewed model run — descriptive results"
    warning = ("Scripted responses and scripted ratings test the software. These numbers cannot compare AI methods or support a research finding."
               if fixture else "Interpret only with the source annotations, raw responses and semantic reviews. These are small-sample descriptive results.")
    body = []
    for row in result["summary"]:
        retained = f'{row["b_retained"]:.0%}' if row["condition"] in {"new", "mixed"} else "not supplied"
        body.append("<tr>" + "".join("<td>" + escape(str(v)) + "</td>" for v in
            (row["method"], row["condition"], row["families"], f'{row["a_retained"]:.0%}', retained,
             f'{row["false_independence"]:.0%}', f'{row["joint_success"]:.0%}')) + "</tr>")
    limitations = "".join("<li>" + escape(item) + "</li>" for item in result["limitations"])
    document = f'''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(headline)}</title>
<style>
:root{{color-scheme:light;background:#f4f6f8;color:#172a3a;font:16px/1.55 system-ui,sans-serif}}
body{{max-width:1080px;margin:0 auto;padding:32px 24px 56px}}h1{{line-height:1.15;font-size:2.4rem;max-width:850px}}
.label{{font-weight:750;text-transform:uppercase;letter-spacing:.08em;color:#315770;font-size:.8rem}}
.warning{{padding:20px;border-left:5px solid #b45309;background:#fff3d6;border-radius:6px}}
.meta{{display:flex;gap:14px;flex-wrap:wrap;margin:24px 0}}.meta span{{background:white;padding:10px 14px;border:1px solid #d5dfe7;border-radius:7px}}
.scroll{{overflow-x:auto;background:white;border:1px solid #d5dfe7;border-radius:9px}}table{{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}}
th,td{{padding:10px 12px;text-align:left;border-bottom:1px solid #e5ebef}}th{{background:#eaf0f5;font-size:.85rem}}td{{font-size:.9rem}}
code{{overflow-wrap:anywhere}}footer{{margin-top:30px;color:#435b6e}}@media(max-width:600px){{body{{padding:22px 14px}}h1{{font-size:1.8rem}}}}
</style><body>
<p class="label">Threat evidence study · pre-event preparation</p><h1>{escape(headline)}</h1>
<p class="warning">{escape(warning)}</p>
<div class="meta"><span>{result["task_count"]} reviewed outputs</span><span>{result["family_count"]} source families</span>
<span>Labels: {escape(result["annotation_status"])}</span><span>{escape(result["model"])}</span></div>
<p>A is the original fact. B is an additional fact. Repeat adds a restatement of A; mixed adds both the restatement and B. Joint success requires retaining all supplied target facts, supported citations, and no unsupported claims or false independence.</p>
<h2>{"Scripted checks" if fixture else "Descriptive outcomes"}</h2>
<div class="scroll"><table><thead><tr><th>Method</th><th>Condition</th><th>Families</th><th>A retained</th><th>B retained</th><th>False independence</th><th>Joint success</th></tr></thead><tbody>{"".join(body)}</tbody></table></div>
<h2>Interpretation limits</h2><ul>{limitations}</ul>
<p>Both document orders are averaged within each family. Each family receives equal weight. No p-values or statistical independence claims are produced.</p>
<footer>Export fingerprint: <code>{escape(result["export_sha256"])}</code><br>Keep results.json, responses.jsonl and reviews.csv with this report. No registration or submission has been performed.</footer>
</body></html>'''
    write_new(output, document)
    return {"report": str(output), "kind": result["kind"]}
