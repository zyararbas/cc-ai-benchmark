"""Command line entry point: `cc-ai-benchmark <command>`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cc_ai_benchmark import __version__
from cc_ai_benchmark.adapters import load_all as load_adapters
from cc_ai_benchmark.adapters.base import available as available_systems
from cc_ai_benchmark.adapters.base import get_adapter
from cc_ai_benchmark.runner import run_suite
from cc_ai_benchmark.runners import available as available_runners
from cc_ai_benchmark.runners import get_runner
from cc_ai_benchmark.scoring import available as available_scorers
from cc_ai_benchmark.scoring import get_scorer
from cc_ai_benchmark.storage import (
    OUTPUT_DIR,
    discover_suites,
    load_suite,
    resolve_suite,
    write_report,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cc-ai-benchmark",
        description="Run reproducible benchmark suites and record the results as JSON.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="list the available suites, runners, and scorers")

    validate = subparsers.add_parser("validate", help="check that every suite file parses")
    validate.add_argument("suite", nargs="?", help="suite name or path (default: all suites)")

    run = subparsers.add_parser("run", help="run a suite and write a report to outputs/")
    run.add_argument("suite", help="suite name (e.g. 'example') or path to a suite JSON file")
    run.add_argument("--runner", default="echo", help="runner to evaluate (default: echo)")
    run.add_argument("--scorer", default="exact_match", help="scorer to use (default: exact_match)")
    run.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help="where to write the report (default: outputs/)",
    )
    run.add_argument("--no-write", action="store_true", help="print the summary without saving")

    subparsers.add_parser("build-bank", help="materialize data/bank/pc-bank.jsonl")

    bench = subparsers.add_parser("bench", help="run systems over the question bank, in parallel")
    bench.add_argument(
        "systems", nargs="+", help="names from config/models.json, or a built-in adapter"
    )
    bench.add_argument("--condition", default="C0", choices=["C0", "C1", "C2", "C3"])
    bench.add_argument("--limit", type=int, help="only the first N items (use for smoke runs)")
    bench.add_argument("--scope", action="append", help="restrict to a scope; repeatable")
    bench.add_argument("--budget", type=float, help="hard ceiling in USD for the whole sweep")
    bench.add_argument("--name", default="sweep", help="report filename suffix")
    bench.add_argument("--no-write", action="store_true")

    verify = subparsers.add_parser(
        "verify", help="one live call per system: proves credentials, ids and parsing"
    )
    verify.add_argument("systems", nargs="+")
    verify.add_argument("--condition", default="C0", choices=["C0", "C1", "C2", "C3"])

    compare = subparsers.add_parser(
        "compare", help="paired comparison of two systems in a sweep report"
    )
    compare.add_argument("report", type=Path)
    compare.add_argument("a")
    compare.add_argument("b")

    models = subparsers.add_parser(
        "models", help="list the model ids a provider will accept (free: no tokens spent)"
    )
    models.add_argument("providers", nargs="*", default=["anthropic", "gemini", "openai"])
    models.add_argument("--filter", help="only ids containing this substring")

    chart = subparsers.add_parser("chart", help="render a sweep report as a standalone HTML page")
    chart.add_argument("report", type=Path)
    chart.add_argument("-o", "--output", type=Path, help="default: alongside the report, .html")

    export = subparsers.add_parser(
        "export", help="flatten a sweep report to one CSV row per question per system"
    )
    export.add_argument("report", type=Path)
    export.add_argument("-o", "--output", type=Path, help="default: alongside the report, .csv")

    return parser


def cmd_list() -> int:
    suites = discover_suites()
    print("Suites:")
    if not suites:
        print("  (none found in data/tasks)")
    for path in suites:
        try:
            suite = load_suite(path)
        except ValueError as exc:
            print(f"  {path.stem:<20} INVALID: {exc}")
            continue
        print(f"  {path.stem:<20} v{suite.version}  {len(suite.tasks)} tasks  {suite.description}")
    load_adapters()
    print(f"\nSystems: {', '.join(available_systems())}")
    print(f"Runners: {', '.join(available_runners())}")
    print(f"Scorers: {', '.join(available_scorers())}")
    return 0


def cmd_validate(reference: str | None) -> int:
    paths = [resolve_suite(reference)] if reference else discover_suites()
    if not paths:
        print("no suite files found in data/tasks", file=sys.stderr)
        return 1
    failed = 0
    for path in paths:
        try:
            suite = load_suite(path)
        except ValueError as exc:
            failed += 1
            print(f"FAIL  {path.name}: {exc}", file=sys.stderr)
        else:
            print(f"ok    {path.name}  ({len(suite.tasks)} tasks)")
    return 1 if failed else 0


def cmd_run(args: argparse.Namespace) -> int:
    suite = load_suite(resolve_suite(args.suite))
    runner = get_runner(args.runner)
    scorer = get_scorer(args.scorer)

    report = run_suite(suite, runner, scorer, runner_name=args.runner)

    print(f"suite   {report.suite} v{report.suite_version}")
    print(f"runner  {report.runner}   scorer  {args.scorer}")
    print(f"tasks   {len(report.results)}")
    print(f"score   {report.mean_score:.3f}")
    errors = [result for result in report.results if result.error]
    if errors:
        print(f"errors  {len(errors)}")
        for result in errors:
            print(f"  {result.task_id}: {result.error}")

    if not args.no_write:
        path = write_report(report, args.output_dir)
        print(f"report  {path}")
    return 0


def _resolve_systems(names: list[str]) -> list:
    from cc_ai_benchmark.systems import build, load_config, placeholders

    load_adapters()
    config = load_config()
    unset = placeholders(config)
    adapters = []
    for name in names:
        if name in config.get("systems", {}):
            adapters.append(build(name, config))
        else:
            adapters.append(get_adapter(name))
    if unset:
        print(
            f"note: {len(unset)} system(s) in config/models.json still need a real model id: "
            f"{', '.join(unset)}",
            file=sys.stderr,
        )
    return adapters


def cmd_build_bank() -> int:
    from cc_ai_benchmark.bank import build_bank, write_bank

    items = build_bank()
    path = write_bank(items)
    flagged = sum(1 for i in items if i.flags)
    print(f"built   {len(items)} items ({flagged} flagged needs-review)")
    print(f"bank    {path}")
    return 0


def cmd_bench(args: argparse.Namespace) -> int:
    from cc_ai_benchmark.bank import load_bank, select
    from cc_ai_benchmark.corpus import recall_at_k
    from cc_ai_benchmark.evalprompt import template_hash
    from cc_ai_benchmark.execute import run_matrix
    from cc_ai_benchmark.report import build_report, print_table, write

    items = select(load_bank(), scopes=args.scope, limit=args.limit)
    if not items:
        print("error: no items selected", file=sys.stderr)
        return 1
    adapters = _resolve_systems(args.systems)

    print(f"bank      {len(items)} items   condition {args.condition}")
    print(f"systems   {', '.join(a.name for a in adapters)}  (running in parallel)")
    if args.budget:
        print(f"budget    ${args.budget:.2f} ceiling")
    print()

    notes = {
        "condition": args.condition,
        "template_hash": template_hash(),
        "selection": {"limit": args.limit, "scopes": args.scope},
    }
    if args.condition == "C2":
        notes["shared_retriever_recall_at_1"] = recall_at_k(items, 1)

    runs = run_matrix(adapters, items, args.condition, budget_usd=args.budget)
    for adapter in adapters:
        adapter.close()

    report = build_report(runs, bank_size=len(items), notes=notes)
    print_table(report)
    for run in runs:
        if run.stopped_early:
            print(f"warning: {run.system} stopped early - {run.stopped_early}", file=sys.stderr)
    if not args.no_write:
        print(f"\nreport  {write(report, name=args.name)}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    from cc_ai_benchmark.adapters.base import Query
    from cc_ai_benchmark.bank import load_bank, select
    from cc_ai_benchmark.corpus import context_for
    from cc_ai_benchmark.evalprompt import render
    from cc_ai_benchmark.grading import grade

    item = select(load_bank(), limit=1)[0]
    failures = 0
    for adapter in _resolve_systems(args.systems):
        context = context_for(item, args.condition)
        system_prompt, user_prompt = render(item, args.condition, context)
        response = adapter.answer(
            Query(
                item=item,
                condition=args.condition,
                prompt=user_prompt,
                system=system_prompt,
                context=context,
            )
        )
        verdict = grade(item, response.text, response.error)
        status = "FAIL" if response.error else "ok"
        if response.error:
            failures += 1
        cost = "-" if response.cost_usd is None else f"${response.cost_usd:.6f}"
        print(f"{status:4} {adapter.name}")
        print(f"     resolved model : {response.model_id}")
        print(
            f"     outcome        : {verdict.outcome}  "
            f"(parsed {verdict.parsed}, expected {item.answer})"
        )
        print(f"     tokens         : {response.usage}")
        print(f"     latency/cost   : {response.latency_ms:.0f}ms / {cost}")
        if response.error:
            print(f"     error          : {response.error}")
        adapter.close()
    return 1 if failures else 0


def cmd_compare(args: argparse.Namespace) -> int:
    import json as _json

    from cc_ai_benchmark.execute import ItemResult
    from cc_ai_benchmark.metrics import mcnemar

    report = _json.loads(args.report.read_text(encoding="utf-8"))
    index = {s["system"]: s for s in report["systems"]}
    for name in (args.a, args.b):
        if name not in index:
            print(f"error: {name!r} not in report (has: {', '.join(index)})", file=sys.stderr)
            return 1

    def load(name: str) -> list:
        return [ItemResult(**{**r, "outcome": r["outcome"]}) for r in index[name]["results"]]

    a_res, b_res = load(args.a), load(args.b)
    a_cond, b_cond = index[args.a]["condition"], index[args.b]["condition"]
    if a_cond != b_cond:
        print(
            f"warning: comparing across conditions ({a_cond} vs {b_cond}) - "
            "this is not a like-for-like result",
            file=sys.stderr,
        )

    stats = mcnemar(a_res, b_res)
    a_acc = index[args.a]["metrics"]["accuracy"]
    b_acc = index[args.b]["metrics"]["accuracy"]
    print(f"{args.a} ({a_cond})  accuracy {a_acc:.3f}")
    print(f"{args.b} ({b_cond})  accuracy {b_acc:.3f}")
    print(f"difference            {a_acc - b_acc:+.3f}")
    print()
    print(f"paired items          {stats['paired_items']}")
    print(f"{args.a} right, {args.b} wrong   {stats['a_correct_b_wrong']}")
    print(f"{args.b} right, {args.a} wrong   {stats['b_correct_a_wrong']}")
    print(f"McNemar exact p       {stats['p_value']:.4g}")
    print()
    if stats["significant_at_05"]:
        print("The difference is unlikely to be chance (p < 0.05).")
    else:
        print("Not resolved by this sample: the difference is within chance.")
    return 0


def cmd_models(args: argparse.Namespace) -> int:
    from cc_ai_benchmark.discover import PROVIDERS, ProviderUnavailable, discover

    unavailable = 0
    for provider in args.providers:
        if provider not in PROVIDERS:
            print(f"error: unknown provider {provider!r}", file=sys.stderr)
            return 1
        print(f"== {provider} ==")
        try:
            rows = discover(provider)
        except ProviderUnavailable as exc:
            unavailable += 1
            print(f"   unavailable - {exc}\n")
            continue
        if args.filter:
            rows = [r for r in rows if args.filter.lower() in r["id"].lower()]
        if not rows:
            print("   (no models matched)\n")
            continue
        for row in rows:
            print(f"   {row['id']:<44} {row['created']:<12} {row['name']}")
        print()
    if unavailable:
        print(
            f"{unavailable} provider(s) could not be listed. Export the missing key and "
            "re-run; listing a catalogue costs nothing.",
            file=sys.stderr,
        )
    return 1 if unavailable == len(args.providers) else 0


def cmd_chart(args: argparse.Namespace) -> int:
    from cc_ai_benchmark.chart import load_report, write_chart

    report = load_report(args.report)
    output = args.output or args.report.with_suffix(".html")
    path = write_chart(report, output)
    systems = ", ".join(s["system"] for s in report["systems"])
    print(f"systems  {systems}")
    print(f"chart    {path}")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    from cc_ai_benchmark.chart import load_report
    from cc_ai_benchmark.export import write_csv

    report = load_report(args.report)
    path, count = write_csv(report, args.output or args.report.with_suffix(".csv"))
    print(f"rows     {count}")
    print(f"csv      {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "list":
            return cmd_list()
        if args.command == "validate":
            return cmd_validate(args.suite)
        if args.command == "run":
            return cmd_run(args)
        if args.command == "build-bank":
            return cmd_build_bank()
        if args.command == "bench":
            return cmd_bench(args)
        if args.command == "verify":
            return cmd_verify(args)
        if args.command == "compare":
            return cmd_compare(args)
        if args.command == "models":
            return cmd_models(args)
        if args.command == "chart":
            return cmd_chart(args)
        if args.command == "export":
            return cmd_export(args)
    except (FileNotFoundError, KeyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
