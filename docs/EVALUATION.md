# Evaluation

## What is measured

The evaluation compares persisted triage results with a small manually labelled set in `backend/data/evaluation_gold.json`.

It currently measures:

- Classification accuracy.
- Per-class and macro precision, recall, and F1 for Actionable, Informational, and Irrelevant.
- Priority-level accuracy.
- Priority confusion matrix, exact agreement, within-one-level agreement, and mean absolute level error.
- Joint classification and priority accuracy.
- Phrase-level action recall and precision.
- Corpus-level action precision and recall across all labelled threads.
- Summary factual-term coverage and complete-case coverage.
- Per-field entity extraction coverage and exact normalised accuracy.
- Coverage: the proportion of gold cases that have been processed into the selected database.

It does not yet score explanation quality, Q&A grounding quality, latency, or cost.

## Running it

From the project root, after processing the sample data:

```powershell
.\.venv\Scripts\python.exe .\backend\evaluate.py
```

The result is written to `artifacts/eval_results/triage_evaluation.json`.

Grounded Q&A has a separate labelled set in `backend/data/qa_evaluation_gold.json`. Evaluate captured responses with:

```powershell
.\.venv\Scripts\python.exe .\backend\evaluate_qa.py --responses .\artifacts\eval_results\qa_responses.json
```

The response file should contain objects with `question_id`, `answer`, and `sources` fields. The evaluator reports answer-term coverage, citation accuracy, unsupported-answer rate, and grounded-answer rate.

## Model comparison

Captured benchmark runs for GPT-4o-mini and GPT-4o can be compared without automatically spending API budget:

```powershell
.\.venv\Scripts\python.exe .\backend\compare_models.py .\artifacts\eval_results\gpt4o_mini.json .\artifacts\eval_results\gpt4o.json
```

Each run should use the same cases and prompt version and contain quality metrics plus a `usage` object with latency, token count, and estimated cost. The comparison output is written to `artifacts/eval_results/model_comparison.json`.

## Prompt-injection evaluation

Adversarial sanitisation cases are stored in `backend/data/prompt_injection_cases.json` and can be run without an API call:

```powershell
.\.venv\Scripts\python.exe .\backend\evaluate_prompt_safety.py
```

The evaluator reports detection accuracy and removal accuracy. The current three-case set is a smoke check, not a complete security benchmark.

## Reading the result

The evaluator deliberately reports coverage separately from accuracy. A result such as 100% accuracy at 62.5% coverage means five of eight labelled cases were available; it does not mean the complete dataset was evaluated.

The current labelled cases cover urgent first-notice claims, routine policy questions, supplier work, informational messages, and irrelevant mail. This is useful as a smoke evaluation but is too small to support production performance claims.

The current eight-case result reports 1.0 precision, recall, and F1 for each classification class and the macro average. This should be read alongside the small sample size and expanded as more labelled cases are added.

Priority is ordinal rather than nominal. The latest result has 87.5% exact agreement, 100% agreement within one level, and a mean absolute level error of 0.125 across the Low/Medium/High scale.

Entity evaluation is reported by field. The current result has 83.3% policy-reference coverage and exact accuracy, and 100% customer-name coverage with 60% exact accuracy. This indicates that the system usually extracts a customer value but often needs name normalisation or better entity resolution.

Across the current labelled set, the evaluator has 84.21% action recall and 77.27% action precision using 19 expected action phrases and 22 predicted actions. This is a phrase-level operational signal, not a semantic equivalence judgement; a stronger benchmark should use reviewer-approved action IDs or an embedding/LLM adjudicator.

Summary evaluation currently reports 95.45% factual-term coverage and 87.5% complete-case coverage across eight labelled summaries. It checks required facts rather than judging style or fluency.

Action labels use phrase-level matching rather than semantic equivalence. Entity scoring currently checks only the labelled fields and exact normalised values. The latest generated metrics are stored in `artifacts/eval_results/triage_evaluation.json` and are also visible in the Operations workspace.

## Evaluation limitations

The labels are manually authored for this prototype. The model can still produce a plausible answer that differs from an operational expert's judgement. A stronger evaluation would use multiple reviewers, agreement measurement, a larger time-separated set, action-level labels, and tests for unsafe or unsupported answers.
