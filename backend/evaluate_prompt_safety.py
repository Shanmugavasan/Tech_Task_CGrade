import argparse
import json
from pathlib import Path

from src.core.prompt_safety import sanitize_untrusted_email


def evaluate(cases_path: Path) -> dict:
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    results = []
    for case in cases:
        sanitized, detected = sanitize_untrusted_email(case["text"])
        results.append({
            "case_id": case["case_id"],
            "detected": detected,
            "detection_correct": detected == case["must_detect"],
            "removed_required_phrases": all(phrase not in sanitized for phrase in case["must_not_contain"]),
        })
    return {
        "case_count": len(results),
        "detection_accuracy": sum(item["detection_correct"] for item in results) / len(results) if results else 0.0,
        "removal_accuracy": sum(item["removed_required_phrases"] for item in results) / len(results) if results else 0.0,
        "case_results": results,
    }


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="Evaluate prompt-injection sanitisation cases.")
    parser.add_argument("--cases", type=Path, default=root / "backend" / "data" / "prompt_injection_cases.json")
    args = parser.parse_args()
    print(json.dumps(evaluate(args.cases), indent=2))


if __name__ == "__main__":
    main()
