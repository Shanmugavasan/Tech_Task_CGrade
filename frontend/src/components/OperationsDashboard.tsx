import { useEffect, useState } from 'react';

interface OperationsSummary {
  provider_metrics: {
    request_count: number;
    success_count: number;
    failure_count: number;
    total_tokens: number;
    estimated_cost_usd: number;
    cache_hit_count: number;
  };
  observability: { langfuse_enabled: boolean; last_error: string | null; project_url: string };
  debounce: { enabled: boolean; settings: { source: string; debounce_minutes: number }[] };
  analytics: Record<string, { sample_count: number; recommended_debounce_minutes: number }>;
  evaluation: {
    evaluated_cases?: number;
    gold_cases?: number;
    coverage?: number;
    metrics?: {
      classification_accuracy?: number;
      priority_level_accuracy?: number;
      joint_classification_priority_accuracy?: number;
    };
    error?: string;
  } | null;
}

interface Props {
  onBack: () => void;
}

export default function OperationsDashboard({ onBack }: Props) {
  const [summary, setSummary] = useState<OperationsSummary | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    fetch('http://localhost:8000/api/operations/summary', { credentials: 'include' })
      .then(response => {
        if (!response.ok) throw new Error();
        return response.json();
      })
      .then(setSummary)
      .catch(() => setError('Unable to load operations data for this session.'));
  }, []);

  if (error) {
    return <main className="mx-auto max-w-5xl px-6 py-10"><button onClick={onBack} className="mb-5 text-sm text-blue-700">← Back to workload</button><div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div></main>;
  }

  if (!summary) return <main className="mx-auto max-w-5xl px-6 py-10 text-sm text-slate-500">Loading operations workspace...</main>;

  const metrics = summary.provider_metrics;
  return (
    <main className="mx-auto max-w-5xl px-6 py-6">
      <button onClick={onBack} className="mb-5 text-sm font-medium text-blue-700 hover:text-blue-900">← Back to workload</button>
      <div className="mb-6 flex items-end justify-between">
        <div><p className="text-xs font-bold uppercase tracking-[0.18em] text-blue-600">Operations workspace</p><h2 className="mt-1 text-2xl font-semibold text-slate-900">AI system health</h2></div>
        <span className={`rounded-full px-3 py-1 text-xs font-semibold ${summary.observability.langfuse_enabled ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'}`}>{summary.observability.langfuse_enabled ? 'LangFuse connected' : 'LangFuse not configured'}</span>
      </div>
      <div className="grid gap-4 sm:grid-cols-3">
        {[
          ['Provider calls', metrics.request_count],
          ['Total tokens', metrics.total_tokens],
          ['Estimated cost', `$${metrics.estimated_cost_usd.toFixed(5)}`],
          ['Failures', metrics.failure_count],
          ['Cache hits', metrics.cache_hit_count],
          ['Debounce', summary.debounce.enabled ? 'Enabled' : 'Disabled'],
        ].map(([label, value]) => <div key={String(label)} className="rounded-xl border border-slate-200 bg-white p-4"><p className="text-2xl font-semibold text-slate-900">{value}</p><p className="mt-1 text-xs uppercase tracking-wider text-slate-500">{label}</p></div>)}
      </div>
      <section className="mt-6 rounded-xl border border-slate-200 bg-white p-5">
        <h3 className="text-sm font-semibold text-slate-900">Debounce policy and evidence</h3>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          {summary.debounce.settings.map(setting => <div key={setting.source} className="flex justify-between rounded-lg bg-slate-50 px-3 py-2 text-sm"><span>{setting.source}</span><span className="font-medium">{setting.debounce_minutes} minutes</span></div>)}
        </div>
        <div className="mt-4 text-xs text-slate-500">Recommendations are calculated from observed follow-up samples and can be applied from the main controls.</div>
      </section>
      <section className="mt-6 rounded-xl border border-slate-200 bg-white p-5">
        <h3 className="text-sm font-semibold text-slate-900">AI evaluation</h3>
        {summary.evaluation?.error ? <p className="mt-2 text-sm text-red-700">{summary.evaluation.error}</p> : summary.evaluation?.metrics ? (
          <>
            <div className="mt-3 grid gap-3 sm:grid-cols-4">
              {[
                ['Classification', summary.evaluation.metrics.classification_accuracy],
                ['Priority', summary.evaluation.metrics.priority_level_accuracy],
                ['Joint', summary.evaluation.metrics.joint_classification_priority_accuracy],
                ['Coverage', summary.evaluation.coverage],
              ].map(([label, value]) => <div key={String(label)} className="rounded-lg bg-slate-50 px-3 py-2"><p className="text-lg font-semibold text-slate-900">{typeof value === 'number' ? `${Math.round(value * 100)}%` : 'n/a'}</p><p className="text-xs uppercase tracking-wider text-slate-500">{label}</p></div>)}
            </div>
            {summary.evaluation.evaluated_cases !== undefined && <p className="mt-3 text-xs text-slate-500">Evaluated {summary.evaluation.evaluated_cases} of {summary.evaluation.gold_cases} labelled cases.</p>}
          </>
        ) : <p className="mt-2 text-sm text-slate-500">No evaluation result has been generated yet.</p>}
      </section>
      <section className="mt-6 rounded-xl border border-slate-200 bg-white p-5">
        <h3 className="text-sm font-semibold text-slate-900">LangFuse</h3>
        <p className="mt-2 text-sm text-slate-600">Traces are sent without raw email content or PII. Use the external LangFuse console for trace exploration.</p>
        <a href={summary.observability.project_url} target="_blank" rel="noreferrer" className="mt-3 inline-block text-sm font-medium text-blue-700 hover:text-blue-900">Open LangFuse console ↗</a>
        {summary.observability.last_error && <p className="mt-2 text-xs text-amber-700">Last telemetry error: {summary.observability.last_error}</p>}
      </section>
    </main>
  );
}
