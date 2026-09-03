"""Tests for the benchmarking path: grading, metrics, adapters, execution."""

import pytest

from cc_ai_benchmark.adapters import load_all
from cc_ai_benchmark.adapters.base import BaseAdapter, Query, Response, get_adapter
from cc_ai_benchmark.bank import Item
from cc_ai_benchmark.execute import run_matrix, run_system
from cc_ai_benchmark.grading import Outcome, grade
from cc_ai_benchmark.metrics import compute, mcnemar

load_all()

ITEM = Item(
    id="pc-99-0001",
    question="Which coverage pays loss of use?",
    choices={"A": "Coverage A", "B": "Coverage B", "C": "Coverage D", "D": "Coverage C"},
    answer="C",
    scope="Homeowners",
    ref="7. Homeowners Insurance.docx",
)
ITEMS = [ITEM, Item(**{**ITEM.to_dict(), "id": "pc-99-0002", "answer": "A"})]


# ---------- grading ----------


@pytest.mark.parametrize(
    "text,expected",
    [
        ('{"answer": "C", "confidence": 0.9}', Outcome.CORRECT),
        ('{"answer":"A"}', Outcome.INCORRECT),
        ('{"answer": null, "confidence": 0.0}', Outcome.ABSTAINED),
        ("The answer is C.", Outcome.CORRECT),
        ("C", Outcome.CORRECT),
        ("(C) Coverage D", Outcome.CORRECT),
        ("Coverage D", Outcome.CORRECT),
        ("I don't know.", Outcome.ABSTAINED),
        ("", Outcome.PARSE_FAILURE),
        ("It depends on the policy.", Outcome.PARSE_FAILURE),
    ],
)
def test_grading_ladder(text, expected):
    assert grade(ITEM, text).outcome is expected


def test_ambiguous_letters_are_a_parse_failure_not_a_guess():
    assert grade(ITEM, "The answer is A. No, the answer is C.").outcome is Outcome.PARSE_FAILURE


def test_transport_error_is_its_own_outcome():
    assert grade(ITEM, "", error="APIConnectionError: boom").outcome is Outcome.ERROR


def test_confidence_is_captured():
    assert grade(ITEM, '{"answer": "C", "confidence": 0.42}').confidence == 0.42


# ---------- metrics ----------


def _run(adapter_name, **kwargs):
    return run_system(get_adapter(adapter_name, **kwargs), ITEMS, "C0")


def test_oracle_is_the_ceiling():
    metrics = compute(_run("oracle").results)
    assert metrics.accuracy == 1.0
    assert metrics.risk_weighted == 1.0


def test_refuser_scores_zero_accuracy_but_zero_risk():
    """Declining everything must not be punished the way being wrong is."""
    metrics = compute(_run("refuser").results)
    assert metrics.accuracy == 0.0
    assert metrics.risk_weighted == 0.0
    assert metrics.abstention_rate == 1.0
    assert metrics.coverage_accuracy == 0.0


def test_risk_weighted_penalizes_confident_error_below_abstention():
    wrong = compute(_run("stub", accuracy=0.0, abstain=0.0, seed=7).results)
    declined = compute(_run("refuser").results)
    assert wrong.risk_weighted < declined.risk_weighted


def test_wilson_interval_brackets_the_estimate():
    metrics = compute(_run("stub", accuracy=0.5, seed=3).results)
    low, high = metrics.accuracy_ci95
    assert low <= metrics.accuracy <= high


# ---------- adapters ----------


def test_stub_is_deterministic_for_a_seed():
    first = [r.outcome for r in _run("stub", accuracy=0.6, seed=11).results]
    second = [r.outcome for r in _run("stub", accuracy=0.6, seed=11).results]
    assert first == second


def test_adapter_converts_exceptions_into_responses():
    """One broken item must never abort a sweep."""

    class Exploding(BaseAdapter):
        name = "exploding"

        def _invoke(self, query: Query) -> Response:
            raise RuntimeError("upstream timeout")

    run = run_system(Exploding(), ITEMS, "C0")
    assert all(r.outcome is Outcome.ERROR for r in run.results)
    assert "upstream timeout" in run.results[0].error


def test_adapter_isolation_no_state_leaks_between_items():
    """The probe that catches a stateful endpoint inflating its own score."""
    seen = []

    class Recording(BaseAdapter):
        name = "recording"

        def _invoke(self, query: Query) -> Response:
            seen.append(query.prompt)
            return Response(text='{"answer": "A"}')

    run_system(Recording(), ITEMS, "C0")
    assert len(seen) == len(ITEMS)
    assert all(ITEMS[0].question in p or ITEMS[1].question in p for p in seen)


def test_grounded_adapter_puts_material_in_front_of_the_model():
    captured = {}

    class Capturing(BaseAdapter):
        name = "capturing"

        def _invoke(self, query: Query) -> Response:
            captured["system"] = query.system
            return Response(text='{"answer": "C"}')

    adapter = get_adapter("grounded", base=Capturing(), strategy="oracle", label="ours")
    response = adapter.answer(Query(item=ITEM, condition="C3", prompt="q"))
    assert response.error is None
    assert "<material>" in captured["system"]
    assert len(captured["system"]) > 1000
    assert adapter.describe()["strategy"] == "oracle"


def test_grounded_rejects_an_unknown_strategy():
    with pytest.raises(ValueError, match="unknown grounding strategy"):
        get_adapter("grounded", base=None, base_system="oracle", strategy="telepathy")


# ---------- parallel execution ----------


def test_run_matrix_runs_every_system_over_the_same_items():
    adapters = [
        get_adapter("stub", label="a", accuracy=0.9, seed=1),
        get_adapter("stub", label="b", accuracy=0.3, seed=2),
        get_adapter("oracle"),
    ]
    runs = run_matrix(adapters, ITEMS, "C0")
    assert {r.system for r in runs} == {"a", "b", "oracle"}
    assert all(len(r.results) == len(ITEMS) for r in runs)
    assert all([r.item_id for r in run.results] == [i.id for i in ITEMS] for run in runs)


def test_budget_ceiling_stops_a_sweep():
    class Pricey(BaseAdapter):
        name = "pricey"
        concurrency = 1

        def _invoke(self, query: Query) -> Response:
            return Response(text='{"answer": "A"}', cost_usd=10.0)

    items = [Item(**{**ITEM.to_dict(), "id": f"pc-99-{n:04d}"}) for n in range(20)]
    run = run_system(
        Pricey(),
        items,
        "C0",
        budget=__import__("cc_ai_benchmark.execute", fromlist=["_Budget"])._Budget(15.0),
    )
    assert run.stopped_early is not None
    assert len(run.results) < len(items)


# ---------- paired comparison ----------


def test_mcnemar_detects_a_real_gap_and_not_a_tie():
    many_items = [Item(**{**ITEM.to_dict(), "id": f"pc-99-{n:04d}"}) for n in range(80)]
    strong = run_system(get_adapter("stub", accuracy=0.95, abstain=0.0, seed=1), many_items, "C0")
    weak = run_system(get_adapter("stub", accuracy=0.05, abstain=0.0, seed=2), many_items, "C0")
    gap = mcnemar(strong.results, weak.results)
    assert gap["discordant"] > 0
    assert gap["p_value"] < 0.05

    same = run_system(get_adapter("oracle"), many_items, "C0")
    tie = mcnemar(same.results, same.results)
    assert tie["discordant"] == 0
    assert tie["p_value"] == 1.0


# ---------- chart ----------


def _report(adapters, **notes):
    from cc_ai_benchmark.report import build_report

    runs = run_matrix(adapters, ITEMS, "C0")
    return build_report(runs, bank_size=len(ITEMS), notes={"template_hash": "abc123", **notes})


def test_chart_renders_a_self_contained_page():
    from cc_ai_benchmark.chart import render

    page = render(_report([get_adapter("oracle"), get_adapter("refuser")]))
    assert "<title>" in page and "<style>" in page
    # A page that only renders against a live CDN is useless at a conference booth.
    assert "http://" not in page and "https://" not in page
    assert "oracle" in page and "refuser" in page


def test_chart_refuses_to_present_mock_adapters_as_a_benchmark():
    from cc_ai_benchmark.chart import render

    page = render(_report([get_adapter("stub", label="pretend-model")]))
    assert "These are not model results" in page


def test_chart_warns_when_conditions_are_mixed():
    from cc_ai_benchmark.chart import render
    from cc_ai_benchmark.report import build_report

    a = run_matrix([get_adapter("stub", label="a", seed=1)], ITEMS, "C0")
    b = run_matrix([get_adapter("stub", label="b", seed=2)], ITEMS, "C3")
    page = render(build_report(a + b, bank_size=len(ITEMS), notes={}))
    assert "Mixed conditions" in page


def test_chart_escapes_scope_and_system_names():
    from cc_ai_benchmark.chart import render

    page = render(_report([get_adapter("stub", label="<script>x</script>")]))
    assert "<script>x</script>" not in page
    assert "&lt;script&gt;" in page


def test_chart_rejects_a_report_that_is_not_a_sweep(tmp_path):
    import json as _json

    from cc_ai_benchmark.chart import load_report

    path = tmp_path / "not-a-sweep.json"
    path.write_text(_json.dumps({"kind": "suite-run"}), encoding="utf-8")
    with pytest.raises(ValueError, match="not a sweep report"):
        load_report(path)


def test_heat_colour_marks_at_or_below_chance_distinctly():
    from cc_ai_benchmark.chart import _heat_colour

    assert _heat_colour(0.20) == _heat_colour(0.25)
    assert _heat_colour(0.95) != _heat_colour(0.25)


# ---------- provider discovery ----------


def test_discovery_reports_a_missing_credential_rather_than_crashing(monkeypatch):
    from cc_ai_benchmark.discover import ProviderUnavailable, discover

    for var in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    for provider in ("anthropic", "gemini", "openai"):
        with pytest.raises(ProviderUnavailable):
            discover(provider)


def test_discovery_rejects_an_unknown_provider():
    from cc_ai_benchmark.discover import discover

    with pytest.raises(ValueError, match="unknown provider"):
        discover("telepathy")


# ---------- per-item export ----------


def test_export_writes_one_row_per_item_per_system_with_token_columns(tmp_path):
    from cc_ai_benchmark.export import write_csv

    report = _report([get_adapter("oracle"), get_adapter("stub", label="s", seed=4)])
    path, count = write_csv(report, tmp_path / "rows.csv")
    assert count == len(ITEMS) * 2

    import csv

    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    assert {r["system"] for r in rows} == {"oracle", "s"}
    assert {r["item_id"] for r in rows} == {i.id for i in ITEMS}
    for row in rows:
        for column in ("prompt_tokens", "completion_tokens", "total_tokens"):
            assert row[column] != ""


def test_export_total_tokens_counts_cached_prompt_tokens_once():
    from cc_ai_benchmark.export import rows

    report = {
        "systems": [
            {
                "system": "x",
                "condition": "C3",
                "adapter": {"model_requested": "m"},
                "results": [
                    {
                        "item_id": "pc-99-0001",
                        "scope": "S",
                        "outcome": "correct",
                        "expected": "A",
                        "usage": {
                            "input_tokens": 100,
                            "cache_read_input_tokens": 900,
                            "output_tokens": 20,
                        },
                    }
                ],
            }
        ]
    }
    row = rows(report)[0]
    assert row["prompt_tokens"] == 100
    assert row["cached_prompt_tokens"] == 900
    assert row["total_tokens"] == 1020
