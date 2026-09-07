import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def _action_metrics(expected: list[str], predicted: list[dict]) -> tuple[float, float]:
    predicted_text = [item.get("task_description", "").lower() for item in predicted]
    expected_terms = [term.lower() for term in expected]
    if not expected_terms:
        return (1.0, 1.0 if not predicted_text else 0.0)

    matched_expected = sum(
        any(term in action for action in predicted_text)
        for term in expected_terms
    )
    matched_predicted = sum(
        any(term in action for term in expected_terms)
        for action in predicted_text
    )
    recall = matched_expected / len(expected_terms)
    precision = matched_predicted / len(predicted_text) if predicted_text else 0.0
    return recall, precision


def _corpus_action_metrics(cases: list[dict]) -> dict:
    expected_total = 0
    matched_expected = 0
    predicted_total = 0
    matched_predicted = 0
    for item in cases:
        expected = [term.lower() for term in item.get("expected_actions", [])]
        predicted = [action.get("task_description", "").lower() for action in item.get("predicted_actions", [])]
        expected_total += len(expected)
        predicted_total += len(predicted)
        matched_expected += sum(any(term in action for action in predicted) for term in expected)
        matched_predicted += sum(any(term in action for term in expected) for action in predicted)
    return {
        "expected_actions": expected_total,
        "predicted_actions": predicted_total,
        "matched_expected_actions": matched_expected,
        "matched_predicted_actions": matched_predicted,
        "recall": matched_expected / expected_total if expected_total else 0.0,
        "precision": matched_predicted / predicted_total if predicted_total else 0.0,
    }


def _summary_metrics(cases: list[dict]) -> dict:
    labelled = [item for item in cases if item.get("summary_terms")]
    matched_terms = sum(item["summary_term_matches"] for item in labelled)
    expected_terms = sum(len(item["summary_terms"]) for item in labelled)
    return {
        "labelled_cases": len(labelled),
        "term_coverage": matched_terms / expected_terms if expected_terms else 0.0,
        "case_coverage": sum(item["summary_term_matches"] == len(item["summary_terms"]) for item in labelled) / len(labelled) if labelled else 0.0,
    }


def _entity_accuracy(expected: dict, predicted: dict) -> float:
    if not expected:
        return 1.0
    matched = sum(
        bool(predicted.get(key)) and str(predicted.get(key)).lower() == str(value).lower()
        for key, value in expected.items()
    )
    return matched / len(expected)


def _entity_metrics(cases: list[dict]) -> dict:
    fields = sorted({
        field
        for item in cases
        for field in item.get("expected_entities", {})
    })
    results = {}
    for field in fields:
        labelled = []
        for item in cases:
            expected = item.get("expected_entities", {})
            if field not in expected:
                continue
            predicted = item.get("predicted_entities", {}).get(field)
            labelled.append({"expected": expected[field], "predicted": predicted})
        matches = sum(
            row["predicted"] is not None
            and str(row["predicted"]).lower() == str(row["expected"]).lower()
            for row in labelled
        )
        results[field] = {
            "labelled_cases": len(labelled),
            "extraction_coverage": sum(row["predicted"] is not None for row in labelled) / len(labelled) if labelled else 0.0,
            "exact_accuracy": matches / len(labelled) if labelled else 0.0,
        }
    return results


def _classification_metrics(cases: list[dict]) -> dict:
    labels = ["Actionable", "Informational", "Irrelevant"]
    metrics = {}
    precisions = []
    recalls = []
    f1_scores = []
    for label in labels:
        true_positive = sum(
            item["expected_classification"] == label
            and item["predicted_classification"] == label
            for item in cases
        )
        false_positive = sum(
            item["expected_classification"] != label
            and item["predicted_classification"] == label
            for item in cases
        )
        false_negative = sum(
            item["expected_classification"] == label
            and item["predicted_classification"] != label
            for item in cases
        )
        precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
        recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        metrics[label] = {"precision": precision, "recall": recall, "f1": f1}
        precisions.append(precision)
        recalls.append(recall)
        f1_scores.append(f1)
    metrics["macro_average"] = {
        "precision": sum(precisions) / len(precisions),
        "recall": sum(recalls) / len(recalls),
        "f1": sum(f1_scores) / len(f1_scores),
    }
    return metrics


def _priority_metrics(cases: list[dict]) -> dict:
    levels = {"Low": 0, "Medium": 1, "High": 2}
    labels = ["Low", "Medium", "High"]
    confusion = {expected: {predicted: 0 for predicted in labels} for expected in labels}
    distances = []
    for item in cases:
        expected = item["expected_priority_level"]
        predicted = item["predicted_priority_level"]
        if expected in levels and predicted in levels:
            confusion[expected][predicted] += 1
            distances.append(abs(levels[expected] - levels[predicted]))
    count = len(distances)
    return {
        "confusion_matrix": confusion,
        "mean_absolute_level_error": sum(distances) / count if count else 0.0,
        "exact_agreement": sum(distance == 0 for distance in distances) / count if count else 0.0,
        "within_one_level": sum(distance <= 1 for distance in distances) / count if count else 0.0,
    }


def evaluate(db_path: Path, gold_path: Path, output_path: Path) -> dict:
    gold_cases = json.loads(gold_path.read_text(encoding="utf-8"))
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT thread_id, current_triage FROM threads"
        ).fetchall()

    predictions = {
        row["thread_id"]: json.loads(row["current_triage"])
        for row in rows
    }
    evaluated = []
    missing_threads = []
    for case in gold_cases:
        prediction = predictions.get(case["thread_id"])
        if prediction is None:
            missing_threads.append(case["thread_id"])
            continue
        predicted_classification = prediction.get("classification")
        predicted_priority = prediction.get("priority_level")
        expected_actions = case.get("expected_actions", [])
        predicted_actions = prediction.get("required_actions", [])
        action_recall, action_precision = _action_metrics(expected_actions, predicted_actions)
        entity_accuracy = _entity_accuracy(
            case.get("expected_entities", {}),
            prediction.get("entities", {}),
        )
        summary = str(prediction.get("one_line_summary", "")).lower()
        summary_terms = case.get("summary_terms", [])
        summary_term_matches = sum(term.lower() in summary for term in summary_terms)
        evaluated.append({
            "thread_id": case["thread_id"],
            "expected_classification": case["classification"],
            "predicted_classification": predicted_classification,
            "expected_priority_level": case["priority_level"],
            "predicted_priority_level": predicted_priority,
            "classification_correct": predicted_classification == case["classification"],
            "priority_level_correct": predicted_priority == case["priority_level"],
            "joint_correct": (
                predicted_classification == case["classification"]
                and predicted_priority == case["priority_level"]
            ),
            "action_recall": action_recall,
            "action_precision": action_precision,
            "entity_accuracy": entity_accuracy,
            "expected_entities": case.get("expected_entities", {}),
            "predicted_entities": prediction.get("entities", {}),
            "expected_actions": expected_actions,
            "predicted_actions": predicted_actions,
            "summary_terms": summary_terms,
            "summary_term_matches": summary_term_matches,
        })

    evaluated_count = len(evaluated)
    classification_correct = sum(item["classification_correct"] for item in evaluated)
    priority_correct = sum(item["priority_level_correct"] for item in evaluated)
    joint_correct = sum(item["joint_correct"] for item in evaluated)
    action_recall = sum(item["action_recall"] for item in evaluated)
    action_precision = sum(item["action_precision"] for item in evaluated)
    entity_accuracy = sum(item["entity_accuracy"] for item in evaluated)
    result = {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "gold_cases": len(gold_cases),
        "evaluated_cases": evaluated_count,
        "coverage": evaluated_count / len(gold_cases) if gold_cases else 0.0,
        "missing_threads": missing_threads,
        "metrics": {
            "classification_accuracy": classification_correct / evaluated_count if evaluated_count else 0.0,
            "priority_level_accuracy": priority_correct / evaluated_count if evaluated_count else 0.0,
            "joint_classification_priority_accuracy": joint_correct / evaluated_count if evaluated_count else 0.0,
            "action_recall": action_recall / evaluated_count if evaluated_count else 0.0,
            "action_precision": action_precision / evaluated_count if evaluated_count else 0.0,
            "entity_accuracy": entity_accuracy / evaluated_count if evaluated_count else 0.0,
        },
        "classification_metrics": _classification_metrics(evaluated),
        "priority_metrics": _priority_metrics(evaluated),
        "entity_metrics": _entity_metrics(evaluated),
        "action_metrics": _corpus_action_metrics(evaluated),
        "summary_metrics": _summary_metrics(evaluated),
        "case_results": evaluated,
        "limitations": [
            "This is a small, manually labelled smoke evaluation, not a statistically representative benchmark.",
            "Action labels use phrase-level matching rather than semantic equivalence, so they are directional rather than definitive.",
            "Entity scoring currently covers only the labelled fields and exact normalised values.",
            "Results depend on the triage records currently persisted in the selected database.",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="Evaluate persisted triage decisions against gold labels.")
    parser.add_argument("--db", type=Path, default=project_root / "backend" / "triage_state.db")
    parser.add_argument("--gold", type=Path, default=project_root / "backend" / "data" / "evaluation_gold.json")
    parser.add_argument("--output", type=Path, default=project_root / "artifacts" / "eval_results" / "triage_evaluation.json")
    args = parser.parse_args()
    result = evaluate(args.db, args.gold, args.output)
    print(json.dumps({"metrics": result["metrics"], "coverage": result["coverage"], "missing_threads": result["missing_threads"]}, indent=2))


if __name__ == "__main__":
    main()
