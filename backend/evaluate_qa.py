import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def evaluate(gold_path: Path, responses_path: Path, output_path: Path) -> dict:
    gold = {item["question_id"]: item for item in json.loads(gold_path.read_text(encoding="utf-8"))}
    responses = {item["question_id"]: item for item in json.loads(responses_path.read_text(encoding="utf-8"))}
    results = []
    for question_id, case in gold.items():
        response = responses.get(question_id)
        if response is None:
            continue
        answer = response.get("answer", "").lower()
        answer_terms = case.get("required_answer_terms", [])
        sources = response.get("sources", [])
        source_threads = {source.get("thread_id") for source in sources}
        answer_term_coverage = sum(term.lower() in answer for term in answer_terms) / len(answer_terms) if answer_terms else 1.0
        citation_correct = all(thread_id in source_threads for thread_id in case.get("required_sources", []))
        unsupported_terms = [term for term in case.get("unsupported_claim_terms", []) if term.lower() in answer]
        results.append({
            "question_id": question_id,
            "answer_term_coverage": answer_term_coverage,
            "citation_correct": citation_correct,
            "unsupported_claims_detected": unsupported_terms,
            "grounded": answer_term_coverage == 1.0 and citation_correct and not unsupported_terms,
        })

    count = len(results)
    output = {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "gold_cases": len(gold),
        "evaluated_cases": count,
        "metrics": {
            "answer_term_coverage": sum(item["answer_term_coverage"] for item in results) / count if count else 0.0,
            "citation_accuracy": sum(item["citation_correct"] for item in results) / count if count else 0.0,
            "unsupported_answer_rate": sum(bool(item["unsupported_claims_detected"]) for item in results) / count if count else 0.0,
            "grounded_answer_rate": sum(item["grounded"] for item in results) / count if count else 0.0,
        },
        "case_results": results,
        "limitations": [
            "Answer scoring uses required-term and forbidden-term checks, not a semantic judge.",
            "A production evaluation should add expert review and claim-level entailment scoring.",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    return output


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="Evaluate grounded Q&A responses against labelled cases.")
    parser.add_argument("--gold", type=Path, default=root / "backend" / "data" / "qa_evaluation_gold.json")
    parser.add_argument("--responses", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=root / "artifacts" / "eval_results" / "qa_evaluation.json")
    args = parser.parse_args()
    result = evaluate(args.gold, args.responses, args.output)
    print(json.dumps(result["metrics"], indent=2))


if __name__ == "__main__":
    main()
