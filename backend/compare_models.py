import argparse
import json
from pathlib import Path


def load_run(path: Path) -> dict:
    result = json.loads(path.read_text(encoding="utf-8"))
    metrics = result.get("metrics", {})
    usage = result.get("usage", {})
    return {
        "model": result.get("model", path.stem),
        "classification_accuracy": metrics.get("classification_accuracy"),
        "priority_level_accuracy": metrics.get("priority_level_accuracy"),
        "action_precision": metrics.get("action_precision"),
        "action_recall": metrics.get("action_recall"),
        "answer_term_coverage": metrics.get("answer_term_coverage"),
        "citation_accuracy": metrics.get("citation_accuracy"),
        "latency_ms": usage.get("latency_ms"),
        "total_tokens": usage.get("total_tokens"),
        "estimated_cost_usd": usage.get("estimated_cost_usd"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare captured model benchmark runs.")
    parser.add_argument("runs", nargs="+", type=Path, help="JSON benchmark result files")
    parser.add_argument("--output", type=Path, default=Path("artifacts/eval_results/model_comparison.json"))
    args = parser.parse_args()
    comparison = {
        "runs": [load_run(path) for path in args.runs],
        "limitations": [
            "This compares captured runs; it does not call a provider automatically.",
            "Models should be compared on the same labelled cases and prompt version.",
            "Cost estimates depend on the pricing assumptions recorded by the provider metrics layer.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(comparison, indent=2), encoding="utf-8")
    print(json.dumps(comparison, indent=2))


if __name__ == "__main__":
    main()
