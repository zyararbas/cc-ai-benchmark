"""Rendering a sweep report as a standalone HTML page.

The numbers already exist in the report JSON. What is missing is their shape:
which systems held up, where each one fell over, and whether a low scope score
is one system's weakness or a scope every system finds hard. That last
distinction is the reason the consensus column exists - a scope the whole field
fails is usually a statement about the questions, not about the models.

No chart library. A report that only renders against a live CDN is a report you
cannot open at a conference booth.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

# Adapters that answer from the key or from a seed rather than from a model.
# A page built on these is a harness demo and has to say so, loudly.
MOCK_KINDS = {"OracleAdapter", "RefuserAdapter", "StubAdapter"}

OUTCOMES: list[tuple[str, str, str]] = [
    ("correct", "Correct", "--correct"),
    ("incorrect", "Wrong", "--wrong"),
    ("abstained", "Declined", "--declined"),
    ("parse_failures", "Unparseable", "--unparsed"),
    ("errors", "Transport error", "--errored"),
]

CHANCE = 0.25  # four choices, always

CSS = """
:root {
  color-scheme: light dark;
  --ground: #f7f6f3;
  --panel: #ffffff;
  --rule: #ddd9d0;
  --ink: #1c1d21;
  --ink-soft: #5d5f68;
  --ink-faint: #8d8f98;
  --accent: #2f4858;
  --correct: #1c7c6b;
  --wrong: #a83f34;
  --declined: #b58324;
  --unparsed: #6b5b95;
  --errored: #6f7379;
  --warn-bg: #fdf3e3;
  --warn-rule: #d9a441;
  --warn-ink: #7a5312;
}
:root:not([data-theme="light"]) { }
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --ground: #16171a;
    --panel: #1e2024;
    --rule: #33363c;
    --ink: #e9e8e4;
    --ink-soft: #a7a9b0;
    --ink-faint: #74777e;
    --accent: #9db6c6;
    --correct: #3fae97;
    --wrong: #d4695c;
    --declined: #d9a441;
    --unparsed: #9887c4;
    --errored: #8b8f96;
    --warn-bg: #2b2412;
    --warn-rule: #a37c26;
    --warn-ink: #e5c584;
  }
}
:root[data-theme="dark"] {
  --ground: #16171a;
  --panel: #1e2024;
  --rule: #33363c;
  --ink: #e9e8e4;
  --ink-soft: #a7a9b0;
  --ink-faint: #74777e;
  --accent: #9db6c6;
  --correct: #3fae97;
  --wrong: #d4695c;
  --declined: #d9a441;
  --unparsed: #9887c4;
  --errored: #8b8f96;
  --warn-bg: #2b2412;
  --warn-rule: #a37c26;
  --warn-ink: #e5c584;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--ground);
  color: var(--ink);
  font: 15px/1.55 ui-sans-serif, -apple-system, "Segoe UI", Roboto, sans-serif;
}
.wrap { max-width: 1100px; margin: 0 auto; padding: 40px 24px 80px; }
h1 {
  font: 600 30px/1.15 ui-serif, Georgia, "Times New Roman", serif;
  letter-spacing: -0.01em;
  margin: 0 0 6px;
  text-wrap: balance;
}
h2 {
  font: 600 13px/1.3 ui-sans-serif, -apple-system, sans-serif;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  color: var(--ink-soft);
  margin: 0 0 14px;
}
section { margin-top: 44px; }
.sub { color: var(--ink-soft); margin: 0 0 4px; }
.provenance {
  font: 12px/1.7 ui-monospace, SFMono-Regular, Menlo, monospace;
  color: var(--ink-faint);
  border-top: 1px solid var(--rule);
  margin-top: 18px;
  padding-top: 12px;
}
.provenance b { color: var(--ink-soft); font-weight: 500; }
.banner {
  background: var(--warn-bg);
  border: 1px solid var(--warn-rule);
  border-left-width: 4px;
  color: var(--warn-ink);
  padding: 14px 18px;
  margin: 22px 0 0;
  border-radius: 3px;
}
.banner strong { display: block; margin-bottom: 3px; }
.panel {
  background: var(--panel);
  border: 1px solid var(--rule);
  border-radius: 4px;
  padding: 22px 24px;
}
.note { color: var(--ink-soft); font-size: 13px; margin: 14px 0 0; }
table { border-collapse: collapse; width: 100%; font-size: 14px; }
th, td { padding: 7px 10px; text-align: right; border-bottom: 1px solid var(--rule); }
th:first-child, td:first-child { text-align: left; }
thead th {
  font: 500 11px/1.3 ui-sans-serif, sans-serif;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--ink-faint);
  border-bottom: 1px solid var(--ink-faint);
}
tbody tr:last-child td { border-bottom: none; }
.num { font-variant-numeric: tabular-nums; font-family: ui-monospace, Menlo, monospace; }
.scroll { overflow-x: auto; }
.bars { display: grid; gap: 14px; }
.bar-row { display: grid; grid-template-columns: 150px 1fr 128px; gap: 14px; align-items: center; }
.bar-name { font-weight: 600; overflow-wrap: anywhere; }
.track {
  position: relative;
  height: 26px;
  background: color-mix(in srgb, var(--ink) 7%, transparent);
  border-radius: 2px;
}
.fill { position: absolute; inset: 0 auto 0 0; background: var(--accent); border-radius: 2px; }
.ci { position: absolute; top: 50%; height: 11px; transform: translateY(-50%); }
.ci::before, .ci::after {
  content: ""; position: absolute; top: 0; width: 1px; height: 11px;
  background: color-mix(in srgb, var(--ink) 62%, transparent);
}
.ci::before { left: 0; } .ci::after { right: 0; }
.ci i {
  position: absolute; top: 50%; left: 0; right: 0; height: 1px;
  background: color-mix(in srgb, var(--ink) 62%, transparent);
}
.chance { position: absolute; top: -3px; bottom: -3px; width: 1px; background: var(--ink-faint); }
.bar-val { text-align: right; font-variant-numeric: tabular-nums; }
.bar-val b { font-size: 17px; font-family: ui-monospace, Menlo, monospace; }
.bar-val span { display: block; font-size: 11px; color: var(--ink-faint); }
.stack { display: flex; height: 22px; border-radius: 2px; overflow: hidden; }
.stack div { height: 100%; }
.legend { display: flex; flex-wrap: wrap; gap: 16px; margin-top: 16px; font-size: 12.5px; }
.legend span { display: flex; align-items: center; gap: 6px; color: var(--ink-soft); }
.swatch { width: 11px; height: 11px; border-radius: 2px; }
.heat th.scope { text-align: left; font-weight: 400; color: var(--ink); max-width: 300px; }
.heat td { text-align: center; padding: 0; border: none; }
.heat .cell {
  padding: 8px 4px;
  font: 500 12.5px ui-monospace, Menlo, monospace;
  color: #16171a;
  border: 1px solid var(--panel);
  border-radius: 2px;
}
.heat .thin { opacity: 0.42; }
.heat tbody tr { border-bottom: 1px solid var(--rule); }
.cards { display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); }
.card { background: var(--panel); border: 1px solid var(--rule);
  border-radius: 4px; padding: 18px 20px; }
.card h3 { margin: 0 0 2px; font-size: 16px; }
.card .kind { font-size: 11.5px; color: var(--ink-faint); margin-bottom: 14px; }
.card dt {
  font: 500 10.5px ui-sans-serif, sans-serif;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: var(--ink-faint);
  margin-top: 12px;
}
.card dl { margin: 0; }
.card ul { margin: 5px 0 0; padding-left: 0; list-style: none; font-size: 13.5px; }
.card li { display: flex; justify-content: space-between; gap: 12px; padding: 2px 0; }
.card li span:last-child { font-family: ui-monospace, Menlo, monospace; color: var(--ink-soft); }
.tag {
  display: inline-block; font-size: 11px; padding: 1px 7px; border-radius: 9px;
  border: 1px solid var(--rule); color: var(--ink-soft); margin-left: 6px;
}
footer { margin-top: 56px; padding-top: 16px; border-top: 1px solid var(--rule);
  font-size: 12px; color: var(--ink-faint); }
"""


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _pct(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:.1f}%"


def _money(value: float | None) -> str:
    return "-" if value is None else f"${value:,.4f}"


def _heat_colour(accuracy: float) -> str:
    """Red below chance, amber through the middle, teal at the top.

    Anchored on chance rather than on zero: for a four-option question, 0.25 is
    the floor a coin reaches, so shading it like a partial success would lie.
    """
    if accuracy <= CHANCE:
        hue, sat, light = 8, 62, 62
    elif accuracy < 0.7:
        span = (accuracy - CHANCE) / (0.7 - CHANCE)
        hue = 8 + span * 37
        sat, light = 62, 62 + span * 6
    else:
        span = (accuracy - 0.7) / 0.3
        hue = 45 + span * 123
        sat = 62 - span * 8
        light = 68 - span * 12
    return f"hsl({hue:.0f} {sat:.0f}% {light:.0f}%)"


def _is_mock(system: dict[str, Any]) -> bool:
    return system.get("adapter", {}).get("kind") in MOCK_KINDS


def _leaderboard(systems: list[dict[str, Any]]) -> str:
    rows = []
    for system in systems:
        metrics = system["metrics"]
        low, high = metrics["accuracy_ci95"]
        accuracy = metrics["accuracy"]
        rows.append(
            f'<div class="bar-row">'
            f'<div class="bar-name">{_esc(system["system"])}'
            f'<span class="tag">{_esc(system["condition"])}</span></div>'
            f'<div class="track">'
            f'<div class="fill" style="width:{accuracy * 100:.2f}%"></div>'
            f'<div class="chance" style="left:{CHANCE * 100:.1f}%"></div>'
            f'<div class="ci" style="left:{low * 100:.2f}%;'
            f'width:{max(high - low, 0.001) * 100:.2f}%"><i></i></div>'
            f"</div>"
            f'<div class="bar-val"><b>{_pct(accuracy)}</b>'
            f"<span>95% CI {_pct(low)} - {_pct(high)}</span></div>"
            f"</div>"
        )
    return f'<div class="bars">{"".join(rows)}</div>'


def _composition(systems: list[dict[str, Any]]) -> str:
    rows = []
    for system in systems:
        metrics = system["metrics"]
        total = max(metrics["n"], 1)
        segments = []
        for key, label, token in OUTCOMES:
            count = metrics.get(key, 0)
            if not count:
                continue
            share = count / total
            segments.append(
                f'<div style="width:{share * 100:.3f}%;background:var({token})" '
                f'title="{_esc(label)}: {count} ({_pct(share)})"></div>'
            )
        rows.append(
            f'<div class="bar-row">'
            f'<div class="bar-name">{_esc(system["system"])}</div>'
            f'<div class="stack">{"".join(segments)}</div>'
            f'<div class="bar-val"><b>{metrics["n"]}</b><span>items</span></div>'
            f"</div>"
        )
    legend = "".join(
        f'<span><i class="swatch" style="background:var({token})"></i>{_esc(label)}</span>'
        for _, label, token in OUTCOMES
    )
    return (
        f'<div class="bars">{"".join(rows)}</div><div class="legend">{legend}</div>'
        '<p class="note">Declined is not a failure. In this domain a system that '
        "abstains costs a referral; one that answers wrong with confidence costs a "
        "claim. Read the amber band against the red one.</p>"
    )


def _scope_matrix(systems: list[dict[str, Any]]) -> tuple[list[str], dict[str, dict[str, Any]]]:
    """scope -> {system: row}, keeping the scope order stable across systems."""
    matrix: dict[str, dict[str, Any]] = {}
    for system in systems:
        for row in system.get("by_scope", []):
            matrix.setdefault(row["scope"], {})[system["system"]] = row
    order = sorted(
        matrix,
        key=lambda scope: (
            sum(r["accuracy"] for r in matrix[scope].values()) / max(len(matrix[scope]), 1)
        ),
    )
    return order, matrix


def _heatmap(systems: list[dict[str, Any]]) -> str:
    order, matrix = _scope_matrix(systems)
    if not order:
        return '<p class="note">No per-scope breakdown in this report.</p>'
    names = [s["system"] for s in systems]
    head = "".join(f"<th>{_esc(name)}</th>" for name in names)
    body = []
    for scope in order:
        cells = []
        accuracies = []
        for name in names:
            row = matrix[scope].get(name)
            if row is None:
                cells.append('<td><div class="cell" style="background:transparent">-</div></td>')
                continue
            accuracies.append(row["accuracy"])
            thin = "" if row.get("reliable", True) else " thin"
            cells.append(
                f'<td><div class="cell{thin}" '
                f'style="background:{_heat_colour(row["accuracy"])}" '
                f'title="n={row["n"]}, abstained {_pct(row["abstention_rate"])}">'
                f"{row['accuracy'] * 100:.0f}</div></td>"
            )
        consensus = sum(accuracies) / len(accuracies) if accuracies else 0.0
        any_row = next(iter(matrix[scope].values()))
        marker = "" if any_row.get("reliable", True) else " *"
        body.append(
            f'<tr><th class="scope">{_esc(scope)}{marker}</th>'
            f'<td class="num">{any_row["n"]}</td>{"".join(cells)}'
            f'<td><div class="cell" style="background:{_heat_colour(consensus)}">'
            f"{consensus * 100:.0f}</div></td></tr>"
        )
    return (
        f'<div class="scroll"><table class="heat"><thead><tr>'
        f'<th class="scope">Scope</th><th>n</th>{head}<th>Field</th>'
        f"</tr></thead><tbody>{''.join(body)}</tbody></table></div>"
        '<p class="note">Accuracy per scope, worst first. The <b>Field</b> column is the '
        "mean across systems: a red cell there is a scope the whole field fails, which is "
        "a claim about the questions - a wrong key, an ambiguous stem, a jurisdictional "
        "edge - at least as often as it is a claim about the models. Faded rows have "
        "fewer than 20 items and are marked with an asterisk; do not read them as a "
        "result.</p>"
    )


def _strengths(systems: list[dict[str, Any]]) -> str:
    cards = []
    for system in systems:
        reliable = [r for r in system.get("by_scope", []) if r.get("reliable", True)]
        reliable.sort(key=lambda r: -r["accuracy"])
        if not reliable:
            continue
        best, worst = reliable[:3], list(reversed(reliable[-3:]))
        metrics = system["metrics"]

        def items(rows: list[dict[str, Any]]) -> str:
            return "".join(
                f"<li><span>{_esc(r['scope'])}</span>"
                f"<span>{r['accuracy'] * 100:.0f}% <small>n={r['n']}</small></span></li>"
                for r in rows
            )

        cards.append(
            f'<div class="card"><h3>{_esc(system["system"])}</h3>'
            f'<div class="kind">{_esc(system.get("adapter", {}).get("kind", "unknown"))} '
            f"&middot; {_esc(system['condition'])} &middot; "
            f"risk-weighted {metrics['risk_weighted']:+.3f} &middot; "
            f"declined {_pct(metrics['abstention_rate'])}</div>"
            f"<dl><dt>Held up</dt><ul>{items(best)}</ul>"
            f"<dt>Fell over</dt><ul>{items(worst)}</ul></dl></div>"
        )
    return f'<div class="cards">{"".join(cards)}</div>' if cards else ""


def _cost_table(systems: list[dict[str, Any]]) -> str:
    rows = []
    for system in systems:
        metrics = system["metrics"]
        rows.append(
            f"<tr><td>{_esc(system['system'])}</td>"
            f'<td class="num">{_pct(metrics["accuracy"])}</td>'
            f'<td class="num">{_pct(metrics["coverage_accuracy"])}</td>'
            f'<td class="num">{metrics["risk_weighted"]:+.3f}</td>'
            f'<td class="num">{_pct(metrics["abstention_rate"])}</td>'
            f'<td class="num">{metrics["tokens_in"]:,}</td>'
            f'<td class="num">{metrics["tokens_out"]:,}</td>'
            f'<td class="num">{_money(metrics["cost_usd"])}</td>'
            f'<td class="num">{_money(metrics["cost_per_correct"])}</td>'
            f'<td class="num">{metrics["latency_p50_ms"]:,.0f}</td>'
            f'<td class="num">{metrics["latency_p95_ms"]:,.0f}</td></tr>'
        )
    return (
        '<div class="scroll"><table><thead><tr><th>System</th><th>Accuracy</th>'
        "<th>Of answered</th><th>Risk-wtd</th><th>Declined</th><th>Tokens in</th>"
        "<th>Tokens out</th><th>Cost</th><th>$ / correct</th><th>p50 ms</th>"
        f"<th>p95 ms</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
        '<p class="note">A dash under cost means no price is configured for that '
        "provider in config/pricing.json. The harness reports nothing rather than "
        "guessing a rate.</p>"
    )


def render(report: dict[str, Any]) -> str:
    systems = sorted(report["systems"], key=lambda s: -s["metrics"]["accuracy"])
    notes = report.get("notes", {})
    mocks = [s["system"] for s in systems if _is_mock(s)]
    stopped = [s["system"] for s in systems if s.get("stopped_early")]

    banners = []
    if mocks:
        banners.append(
            '<div class="banner"><strong>These are not model results.</strong>'
            f"{_esc(', '.join(mocks))} "
            f"{'is' if len(mocks) == 1 else 'are'} built-in mock adapters that answer "
            "from the answer key or from a seed. This page demonstrates the reporting "
            "path; it says nothing about any model. Do not show it as a benchmark.</div>"
        )
    if stopped:
        banners.append(
            '<div class="banner"><strong>Incomplete sweep.</strong>'
            f"{_esc(', '.join(stopped))} stopped early against the budget ceiling, so "
            "the sample is truncated and not comparable with a full pass.</div>"
        )

    conditions = sorted({s["condition"] for s in systems})
    if len(conditions) > 1:
        banners.append(
            '<div class="banner"><strong>Mixed conditions.</strong>'
            f"This page compares systems run under {_esc(', '.join(conditions))}. "
            "Those are different exams. Read each condition on its own.</div>"
        )

    provenance = [
        ("Generated", report.get("generated_at", "-")),
        ("Harness", report.get("harness_version", "-")),
        ("Bank", f"{report.get('bank_size', '-')} items"),
        ("Condition", ", ".join(conditions) or "-"),
        ("Prompt template", notes.get("template_hash", "-")),
    ]
    if "shared_retriever_recall_at_1" in notes:
        provenance.append(("Retriever recall@1", f"{notes['shared_retriever_recall_at_1']:.3f}"))
    provenance_html = "<br>".join(f"<b>{_esc(k)}</b> &nbsp;{_esc(v)}" for k, v in provenance)

    return f"""<title>P&C Benchmark Results</title>
<style>{CSS}</style>
<div class="wrap">
<header>
  <h1>Where each system held up, and where it fell over</h1>
  <p class="sub">Property &amp; casualty licensing questions, {report.get("bank_size", "-")} items,
     {len(systems)} system{"" if len(systems) == 1 else "s"}.</p>
  {"".join(banners)}
  <div class="provenance">{provenance_html}</div>
</header>

<section>
  <h2>Accuracy</h2>
  <div class="panel">{_leaderboard(systems)}
  <p class="note">Whiskers are 95% Wilson intervals; the thin vertical line is chance
     for a four-option question. Two bars whose intervals overlap have not been
     separated by this sample - use <code>compare</code> for the paired test.</p></div>
</section>

<section>
  <h2>What each answer turned into</h2>
  <div class="panel">{_composition(systems)}</div>
</section>

<section>
  <h2>By scope</h2>
  <div class="panel">{_heatmap(systems)}</div>
</section>

<section>
  <h2>Strengths and weaknesses</h2>
  {_strengths(systems)}
</section>

<section>
  <h2>Cost and latency</h2>
  <div class="panel">{_cost_table(systems)}</div>
</section>

<footer>Generated by cc-ai-benchmark {_esc(report.get("harness_version", ""))} from a sweep
report. Every number here is recomputable from the JSON it was rendered from.</footer>
</div>
"""


def write_chart(report: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(report), encoding="utf-8")
    return path


def load_report(path: Path) -> dict[str, Any]:
    report = json.loads(path.read_text(encoding="utf-8"))
    if report.get("kind") != "sweep":
        raise ValueError(f"{path} is not a sweep report (kind={report.get('kind')!r})")
    return report
