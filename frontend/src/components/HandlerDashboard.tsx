import { useState } from 'react';
import { type ThreadState } from '../hooks/useWebSocket';
import ThreadDetailPanel from './ThreadDetailPanel';

interface Props {
  threads: ThreadState[];
}

const PRIORITY_LEFT: Record<string, string> = {
  high: 'border-l-red-500',
  medium: 'border-l-amber-400',
  low: 'border-l-emerald-400',
};

const PRIORITY_BADGE: Record<string, string> = {
  high: 'bg-red-50 text-red-700 border-red-200',
  medium: 'bg-amber-50 text-amber-700 border-amber-200',
  low: 'bg-emerald-50 text-emerald-700 border-emerald-200',
};

interface QASource { thread_id: string; message_id: string; subject: string; sent_from: string; date_sent: string; }
interface QAMessage { role: 'user' | 'assistant'; text: string; sources?: QASource[]; }

export default function HandlerDashboard({ threads }: Props) {
  const [selectedThread, setSelectedThread] = useState<ThreadState | null>(null);
  const [activeTab, setActiveTab] = useState<'workload' | 'archive' | 'irrelevant'>('workload');
  const [globalQ, setGlobalQ] = useState('');
  const [globalQA, setGlobalQA] = useState<QAMessage[]>([]);
  const [globalLoading, setGlobalLoading] = useState(false);

  const actionable = threads.filter(t => t.current_triage.classification === 'Actionable');
  const informational = threads.filter(t => t.current_triage.classification === 'Informational');
  const irrelevant = threads.filter(t => t.current_triage.classification === 'Irrelevant');
  const high = actionable.filter(t => t.current_triage.priority_level.toLowerCase() === 'high').length;
  const medium = actionable.filter(t => t.current_triage.priority_level.toLowerCase() === 'medium').length;
  const pendingActions = actionable.reduce((sum, t) => sum + t.current_triage.required_actions.filter(a => !a.is_resolved).length, 0);

  const visibleThreads = activeTab === 'workload'
    ? actionable
    : activeTab === 'archive'
      ? informational
      : irrelevant;

  const handleGlobalAsk = async () => {
    const q = globalQ.trim();
    if (!q) return;
    setGlobalQA(prev => [...prev, { role: 'user', text: q }]);
    setGlobalQ('');
    setGlobalLoading(true);
    try {
      const res = await fetch('http://localhost:8000/api/qa', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q }),
      });
      const data = await res.json();
      setGlobalQA(prev => [...prev, { role: 'assistant', text: data.answer, sources: data.sources }]);
    } catch {
      setGlobalQA(prev => [...prev, { role: 'assistant', text: 'Error reaching Q&A service.' }]);
    } finally {
      setGlobalLoading(false);
    }
  };

  if (threads.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-gray-400">
        <div className="w-10 h-10 rounded-full border-4 border-gray-200 border-t-blue-500 animate-spin mb-5" />
        <p className="text-base">Waiting for incoming emails — press Play to start.</p>
      </div>
    );
  }

  return (
    <>
      <div className="px-6 pt-6 pb-2 space-y-5">

        {/* Stats */}
        <div className="grid grid-cols-4 gap-4">
          {[
            { label: 'Actionable threads', value: actionable.length, color: 'text-gray-800' },
            { label: 'High priority', value: high, color: 'text-red-600' },
            { label: 'Medium priority', value: medium, color: 'text-amber-600' },
            { label: 'Pending actions', value: pendingActions, color: 'text-blue-700' },
          ].map(stat => (
            <div key={stat.label} className="bg-white rounded-xl border border-gray-200 px-4 py-3">
              <p className={`text-2xl font-bold ${stat.color}`}>{stat.value}</p>
              <p className="text-xs text-gray-400 mt-0.5">{stat.label}</p>
            </div>
          ))}
        </div>

        {/* Global Q&A */}
        <div className="bg-white rounded-xl border border-gray-200 px-5 py-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-1">Ask about your workload</h3>
          <p className="text-xs text-gray-400 mb-3">Query across all threads — e.g. "Any action needed for Broker X?" or "Which high-priority claims need an adjuster?"</p>
          {globalQA.length > 0 && (
            <div className="space-y-2 mb-3 max-h-40 overflow-y-auto">
              {globalQA.map((m, i) => (
                <div key={i} className={`rounded-lg px-3 py-2 text-sm ${m.role === 'user' ? 'bg-blue-50 text-blue-900 ml-10' : 'bg-slate-50 text-slate-800 mr-10 border border-slate-200'}`}>
                  {m.text}
                  {m.sources && m.sources.length > 0 && (
                    <div className="mt-2 border-t border-slate-200 pt-2 text-xs text-slate-500">
                      Sources: {m.sources.map(source => `${source.thread_id} / ${source.message_id}`).join(', ')}
                    </div>
                  )}
                </div>
              ))}
              {globalLoading && (
                <div className="bg-slate-50 rounded-lg px-3 py-2 text-sm text-slate-400 mr-10 border border-slate-200 animate-pulse">Thinking...</div>
              )}
            </div>
          )}
          <div className="flex gap-2">
            <input
              type="text"
              value={globalQ}
              onChange={e => setGlobalQ(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleGlobalAsk()}
              placeholder='e.g. "Was there any action required for Broker X?"'
              className="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <button
              onClick={handleGlobalAsk}
              disabled={!globalQ.trim() || globalLoading}
              className="bg-[#004fb6] text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-800 disabled:opacity-40 transition-colors"
            >
              Ask
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 bg-gray-100 rounded-lg p-1 w-fit">
          <button
            onClick={() => setActiveTab('workload')}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${activeTab === 'workload' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'}`}
          >
            Workload
            <span className={`ml-2 px-1.5 py-0.5 rounded-full text-xs ${activeTab === 'workload' ? 'bg-blue-100 text-blue-700' : 'bg-gray-200 text-gray-500'}`}>
              {actionable.length}
            </span>
          </button>
          <button
            onClick={() => setActiveTab('archive')}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${activeTab === 'archive' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'}`}
          >
            Informational
            <span className={`ml-2 px-1.5 py-0.5 rounded-full text-xs ${activeTab === 'archive' ? 'bg-slate-100 text-slate-600' : 'bg-gray-200 text-gray-500'}`}>
              {informational.length}
            </span>
          </button>
          <button
            onClick={() => setActiveTab('irrelevant')}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${activeTab === 'irrelevant' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'}`}
          >
            Irrelevant
            <span className={`ml-2 px-1.5 py-0.5 rounded-full text-xs ${activeTab === 'irrelevant' ? 'bg-gray-200 text-gray-700' : 'bg-gray-200 text-gray-500'}`}>
              {irrelevant.length}
            </span>
          </button>
        </div>

        {/* Thread list */}
        <div className="space-y-2 pb-10">
          {visibleThreads.length === 0 && (
            <div className="text-center py-10 text-gray-400 text-sm">
              {activeTab === 'workload'
                ? 'No actionable threads yet.'
                : activeTab === 'archive'
                  ? 'No informational emails yet.'
                  : 'No irrelevant emails to review.'}
            </div>
          )}
          {visibleThreads.map(thread => {
            const t = thread.current_triage;
            const pk = t.priority_level.toLowerCase();
            const borderColor = PRIORITY_LEFT[pk] ?? PRIORITY_LEFT.low;
            const badgeColor = PRIORITY_BADGE[pk] ?? PRIORITY_BADGE.low;
            const entities = t.entities ?? {};
            const showScore = t.priority_score > 0;

            return (
              <button
                key={thread.thread_id}
                onClick={() => setSelectedThread(thread)}
                className={`w-full text-left bg-white rounded-xl border border-gray-200 border-l-4 ${borderColor} px-5 py-4 hover:shadow-md hover:border-gray-300 transition-all group`}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                      {activeTab === 'workload' && (
                        <span className={`px-2 py-0.5 rounded-full text-xs font-semibold border ${badgeColor}`}>
                          {t.priority_level.toUpperCase()}{showScore ? ` · ${t.priority_score}` : ''}
                        </span>
                      )}
                      {activeTab === 'archive' && (
                        <span className="px-2 py-0.5 rounded-full text-xs font-medium border bg-slate-100 text-slate-600 border-slate-200">
                          Informational
                        </span>
                      )}
                      {activeTab === 'irrelevant' && (
                        <span className="px-2 py-0.5 rounded-full text-xs font-medium border bg-gray-100 text-gray-600 border-gray-200">
                          Irrelevant
                        </span>
                      )}
                      {entities.policy_reference && (
                        <span className="text-xs font-mono text-gray-400">{entities.policy_reference}</span>
                      )}
                    </div>
                    <p className="text-sm font-medium text-gray-900 leading-snug line-clamp-2">{t.one_line_summary}</p>
                    {(entities.customer_name || entities.broker_name) && (
                      <p className="text-xs text-gray-400 mt-1.5">
                        {[entities.customer_name, entities.broker_name].filter(Boolean).join(' · ')}
                      </p>
                    )}
                  </div>
                  <div className="shrink-0 text-right">
                    <p className="text-xs text-gray-400 whitespace-nowrap">
                      {new Date(thread.last_updated).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </p>
                    <p className="text-xs text-gray-400 mt-1">{thread.message_count} msg</p>
                    {t.required_actions.length > 0 && (
                      <p className="text-xs font-medium text-blue-600 mt-1">
                        {t.required_actions.length} action{t.required_actions.length !== 1 ? 's' : ''}
                      </p>
                    )}
                    <p className="text-xs text-gray-300 mt-1.5 group-hover:text-blue-400 transition-colors">Open →</p>
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      <ThreadDetailPanel
        thread={selectedThread}
        onClose={() => setSelectedThread(null)}
        onThreadUpdated={updatedThread => setSelectedThread(updatedThread)}
      />
    </>
  );
}