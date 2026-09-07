import { useEffect, useState } from 'react';
import { type ThreadState } from '../hooks/useWebSocket';

interface Props {
  thread: ThreadState | null;
  onClose: () => void;
  onThreadUpdated: (thread: ThreadState) => void;
}

interface QAMessage {
  role: 'user' | 'assistant';
  text: string;
  sources?: QASource[];
}

interface QASource {
  thread_id: string;
  message_id: string;
  subject: string;
  sent_from: string;
  date_sent: string;
}

interface AuditEvent {
  event_id: number;
  occurred_at: string;
  step: string;
  message_id?: string;
  model?: string;
  prompt_version?: string;
  details: Record<string, unknown>;
}

interface ReplyDraft {
  draft_id: string;
  thread_id: string;
  draft_type: 'external_reply' | 'internal_note';
  body: string;
  status: 'pending' | 'approved' | 'rejected';
  created_at: string;
  updated_at: string;
}

const PRIORITY_COLORS: Record<string, string> = {
  high: 'bg-red-100 text-red-800 border-red-200',
  medium: 'bg-amber-100 text-amber-800 border-amber-200',
  low: 'bg-green-100 text-green-800 border-green-200',
};

const CLASS_BORDER: Record<string, string> = {
  Actionable: 'border-l-blue-500',
  Informational: 'border-l-slate-400',
  Irrelevant: 'border-l-gray-300',
};

export default function ThreadDetailPanel({ thread, onClose, onThreadUpdated }: Props) {
  const [qaInput, setQaInput] = useState('');
  const [qaMessages, setQaMessages] = useState<QAMessage[]>([]);
  const [qaLoading, setQaLoading] = useState(false);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [editingActionId, setEditingActionId] = useState<string | null>(null);
  const [actionDraft, setActionDraft] = useState('');
  const [actionSavingId, setActionSavingId] = useState<string | null>(null);
  const [noteDraft, setNoteDraft] = useState('');
  const [noteSaving, setNoteSaving] = useState(false);
  const [replyDrafts, setReplyDrafts] = useState<ReplyDraft[]>([]);
  const [draftLoading, setDraftLoading] = useState(false);
  const [overrideReason, setOverrideReason] = useState('');
  const [overrideLoading, setOverrideLoading] = useState(false);
  const [overrideClassification, setOverrideClassification] = useState('');
  const [overridePriority, setOverridePriority] = useState('');

  useEffect(() => {
    if (!thread) {
      return;
    }

    fetch(`http://localhost:8000/api/threads/${thread.thread_id}/audit`, { credentials: 'include' })
      .then(response => response.ok ? response.json() : [])
      .then((events: AuditEvent[]) => setAuditEvents(events))
      .catch(() => setAuditEvents([]));

    fetch(`http://localhost:8000/api/threads/${thread.thread_id}/drafts`, { credentials: 'include' })
      .then(response => response.ok ? response.json() : [])
      .then((drafts: ReplyDraft[]) => setReplyDrafts(drafts))
      .catch(() => setReplyDrafts([]));
  }, [thread]);

  const generateDraft = async (draftType: ReplyDraft['draft_type']) => {
    if (!thread) return;
    setDraftLoading(true);
    try {
      const response = await fetch(`http://localhost:8000/api/threads/${thread.thread_id}/drafts`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ draft_type: draftType }),
      });
      if (!response.ok) throw new Error('Draft generation failed');
      const draft = await response.json() as ReplyDraft;
      setReplyDrafts(previous => [draft, ...previous]);
    } finally {
      setDraftLoading(false);
    }
  };

  const updateDraft = async (draftId: string, changes: Partial<Pick<ReplyDraft, 'body' | 'status'>>) => {
    const response = await fetch(`http://localhost:8000/api/drafts/${draftId}`, {
      method: 'PATCH',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(changes),
    });
    if (!response.ok) return;
    const updated = await response.json() as ReplyDraft;
    setReplyDrafts(previous => previous.map(draft => draft.draft_id === draftId ? updated : draft));
  };

  const saveOverride = async (changes: Record<string, unknown>) => {
    if (!thread || !overrideReason.trim()) return;
    setOverrideLoading(true);
    try {
      const response = await fetch(`http://localhost:8000/api/threads/${thread.thread_id}/triage`, {
        method: 'PATCH',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...changes, reason: overrideReason }),
      });
      if (!response.ok) throw new Error('Override failed');
      onThreadUpdated(await response.json() as ThreadState);
      setOverrideReason('');
    } finally {
      setOverrideLoading(false);
    }
  };

  const updateAction = async (actionId: string, changes: Record<string, unknown>) => {
    if (!thread) return;
    setActionSavingId(actionId);
    try {
      const response = await fetch(`http://localhost:8000/api/threads/${thread.thread_id}/actions/${actionId}`, {
        method: 'PATCH',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(changes),
      });
      if (!response.ok) throw new Error('Action update failed');
      const updatedThread = await response.json() as ThreadState;
      onThreadUpdated(updatedThread);
      setEditingActionId(null);
    } finally {
      setActionSavingId(null);
    }
  };

  const addNote = async () => {
    if (!thread || !noteDraft.trim()) return;
    setNoteSaving(true);
    try {
      const response = await fetch(`http://localhost:8000/api/threads/${thread.thread_id}/notes`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ note: noteDraft }),
      });
      if (!response.ok) throw new Error('Note update failed');
      onThreadUpdated(await response.json() as ThreadState);
      setNoteDraft('');
    } finally {
      setNoteSaving(false);
    }
  };

  const deleteNote = async (noteIndex: number) => {
    if (!thread) return;
    const response = await fetch(`http://localhost:8000/api/threads/${thread.thread_id}/notes/${noteIndex}`, { method: 'DELETE', credentials: 'include' });
    if (!response.ok) return;
    onThreadUpdated(await response.json() as ThreadState);
  };

  const handleAsk = async () => {
    const q = qaInput.trim();
    if (!q || !thread) return;
    setQaMessages(prev => [...prev, { role: 'user', text: q }]);
    setQaInput('');
    setQaLoading(true);
    try {
      const res = await fetch('http://localhost:8000/api/qa', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q, thread_id: thread.thread_id }),
      });
      const data = await res.json();
      setQaMessages(prev => [...prev, { role: 'assistant', text: data.answer, sources: data.sources }]);
    } catch {
      setQaMessages(prev => [...prev, { role: 'assistant', text: 'Error reaching the Q&A service.' }]);
    } finally {
      setQaLoading(false);
    }
  };

  if (!thread) return null;

  const { current_triage: t } = thread;
  const entities = t.entities ?? {};
  const priorityKey = t.priority_level.toLowerCase();
  const borderColor = CLASS_BORDER[t.classification] ?? 'border-l-gray-300';

  return (
    <div className="fixed inset-0 z-40 flex justify-end" onClick={onClose}>
      <div
        className="relative w-full max-w-2xl h-full bg-white shadow-2xl flex flex-col overflow-hidden"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className={`border-l-4 ${borderColor} bg-slate-50 px-6 py-4 border-b border-gray-200`}>
          <div className="flex justify-between items-start">
            <div className="flex-1 min-w-0 pr-4">
              <p className="text-xs font-mono text-gray-400 mb-1">{thread.thread_id}</p>
              <h2 className="text-base font-semibold text-gray-900 leading-snug">{t.one_line_summary}</h2>
            </div>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600 mt-0.5 shrink-0">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12"/></svg>
            </button>
          </div>

          {/* Badges */}
          <div className="flex flex-wrap gap-2 mt-3">
            <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold border ${PRIORITY_COLORS[priorityKey] ?? PRIORITY_COLORS.low}`}>
              {t.priority_level} · {t.priority_score}
            </span>
            <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold border bg-blue-50 text-blue-700 border-blue-200">
              {t.classification}
            </span>
            <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold border bg-slate-100 text-slate-600 border-slate-200">
              {thread.message_count} {thread.message_count === 1 ? 'message' : 'messages'}
            </span>
            <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold border bg-slate-100 text-slate-600 border-slate-200">
              {thread.handler_type}
            </span>
          </div>

          {(t.classification_reasoning || t.urgency_justification) && (
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              {t.classification_reasoning && (
                <div className="rounded-lg border border-blue-100 bg-blue-50 px-3 py-2.5">
                  <p className="text-xs font-bold uppercase tracking-wider text-blue-500">Classification rationale</p>
                  <p className="mt-1 text-sm text-blue-950">{t.classification_reasoning}</p>
                </div>
              )}
              {t.urgency_justification && (
                <div className="rounded-lg border border-amber-100 bg-amber-50 px-3 py-2.5">
                  <p className="text-xs font-bold uppercase tracking-wider text-amber-600">Priority rationale</p>
                  <p className="mt-1 text-sm text-amber-950">{t.urgency_justification}</p>
                </div>
              )}
            </div>
          )}
          <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
            <span>Classification confidence: {Math.round(t.classification_confidence * 100)}%</span>
            <span>Calibrated confidence: {Math.round(t.calibrated_confidence * 100)}%</span>
            {t.classification === 'Actionable' ? (
              <>
                <span>Extraction confidence: {Math.round(t.extraction_confidence * 100)}%</span>
                <span>Priority confidence: {Math.round(t.priority_confidence * 100)}%</span>
              </>
            ) : (
              <span>Extraction and priority: not applicable</span>
            )}
          </div>
          <div className="mt-3 rounded-lg border border-slate-200 bg-white px-3 py-2.5">
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="font-semibold text-slate-600">Handler override</span>
              <span className="text-slate-500">Classification: {t.classification_source}</span>
              <span className="text-slate-500">Priority: {t.priority_source}</span>
            </div>
            {t.override_reason && <p className="mt-1 text-xs text-slate-500">Reason: {t.override_reason}</p>}
            <div className="mt-2 flex flex-wrap gap-2">
              <select
                value={overrideClassification}
                disabled={overrideLoading}
                onChange={event => setOverrideClassification(event.target.value)}
                className="rounded border border-slate-200 px-2 py-1 text-xs"
                aria-label="Override classification"
              >
                <option value="">Override classification</option>
                <option value="Actionable">Actionable</option>
                <option value="Informational">Informational</option>
                <option value="Irrelevant">Irrelevant</option>
              </select>
              <select
                value={overridePriority}
                disabled={overrideLoading}
                onChange={event => setOverridePriority(event.target.value)}
                className="rounded border border-slate-200 px-2 py-1 text-xs"
                aria-label="Override priority"
              >
                <option value="">Override priority</option>
                <option value="High">High</option>
                <option value="Medium">Medium</option>
                <option value="Low">Low</option>
              </select>
              <input
                value={overrideReason}
                onChange={event => setOverrideReason(event.target.value)}
                placeholder="Reason required before override"
                className="min-w-[12rem] flex-1 rounded border border-slate-200 px-2 py-1 text-xs"
              />
              <button
                onClick={() => saveOverride({
                  ...(overrideClassification ? { classification: overrideClassification } : {}),
                  ...(overridePriority ? { priority_level: overridePriority } : {}),
                })}
                disabled={overrideLoading || !overrideReason.trim() || (!overrideClassification && !overridePriority)}
                className="rounded bg-slate-700 px-3 py-1 text-xs font-medium text-white hover:bg-slate-900 disabled:opacity-40"
              >
                Apply override
              </button>
            </div>
          </div>
        </div>

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">

          {/* Entities */}
          {(entities.policy_reference || entities.customer_name || entities.broker_name || (entities.third_parties?.length ?? 0) > 0) && (
            <section>
              <h3 className="text-xs font-bold uppercase tracking-wider text-gray-400 mb-3">Extracted entities</h3>
              <div className="grid grid-cols-2 gap-3">
                {entities.policy_reference && (
                  <div className="bg-slate-50 rounded-lg px-3 py-2.5 border border-slate-100">
                    <p className="text-xs text-slate-400 mb-0.5">Policy reference</p>
                    <p className="text-sm font-mono font-medium text-slate-800">{entities.policy_reference}</p>
                  </div>
                )}
                {entities.customer_name && (
                  <div className="bg-slate-50 rounded-lg px-3 py-2.5 border border-slate-100">
                    <p className="text-xs text-slate-400 mb-0.5">Customer</p>
                    <p className="text-sm font-medium text-slate-800">{entities.customer_name}</p>
                  </div>
                )}
                {entities.broker_name && (
                  <div className="bg-slate-50 rounded-lg px-3 py-2.5 border border-slate-100">
                    <p className="text-xs text-slate-400 mb-0.5">Broker</p>
                    <p className="text-sm font-medium text-slate-800">{entities.broker_name}</p>
                  </div>
                )}
                {(entities.third_parties?.length ?? 0) > 0 && (
                  <div className="bg-slate-50 rounded-lg px-3 py-2.5 border border-slate-100">
                    <p className="text-xs text-slate-400 mb-0.5">Third parties</p>
                    <p className="text-sm font-medium text-slate-800">{entities.third_parties.join(', ')}</p>
                  </div>
                )}
              </div>
            </section>
          )}

          {/* Required actions */}
          {t.required_actions.length > 0 && (
            <section>
              <h3 className="text-xs font-bold uppercase tracking-wider text-gray-400 mb-3">Required actions</h3>
              <ul className="space-y-2">
                {t.required_actions.map((action, idx) => (
                  <li key={action.action_id || idx} className="flex items-start gap-3 bg-white border border-gray-100 rounded-lg px-3 py-2.5 hover:border-blue-200 transition-colors">
                    <input
                      type="checkbox"
                      checked={action.is_resolved}
                      disabled={actionSavingId === action.action_id}
                      onChange={event => updateAction(action.action_id, { is_resolved: event.target.checked })}
                      className="mt-0.5 h-4 w-4 shrink-0 accent-blue-600"
                      aria-label={`Mark action ${idx + 1} as ${action.is_resolved ? 'open' : 'resolved'}`}
                    />
                    <div className="flex-1 min-w-0">
                      {editingActionId === action.action_id ? (
                        <div className="flex gap-2">
                          <input
                            value={actionDraft}
                            onChange={event => setActionDraft(event.target.value)}
                            className="min-w-0 flex-1 rounded border border-blue-300 px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                            autoFocus
                          />
                          <button
                            onClick={() => updateAction(action.action_id, { task_description: actionDraft })}
                            disabled={!actionDraft.trim() || actionSavingId === action.action_id}
                            className="text-xs font-medium text-blue-700 disabled:opacity-40"
                          >
                            Save
                          </button>
                          <button
                            onClick={() => setEditingActionId(null)}
                            className="text-xs text-gray-500"
                          >
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <div className="flex items-start justify-between gap-2">
                          <p className={`text-sm ${action.is_resolved ? 'text-gray-400 line-through' : 'text-gray-800'}`}>
                            {action.task_description}
                          </p>
                          <button
                            onClick={() => { setEditingActionId(action.action_id); setActionDraft(action.task_description); }}
                            className="shrink-0 text-xs font-medium text-blue-600 hover:text-blue-800"
                          >
                            Edit
                          </button>
                        </div>
                      )}
                      {action.deadline && (
                        <p className="text-xs font-semibold text-red-600 mt-0.5">
                          SLA: {action.deadline}
                        </p>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section>
            <h3 className="text-xs font-bold uppercase tracking-wider text-gray-400 mb-3">Internal notes</h3>
            {thread.internal_notes.length > 0 && (
              <ul className="mb-3 space-y-2">
                {thread.internal_notes.map((note, index) => (
                  <li key={`${index}-${note}`} className="flex items-start justify-between gap-3 rounded-lg border border-yellow-100 bg-yellow-50 px-3 py-2.5">
                    <p className="text-sm text-yellow-950">{note}</p>
                    <button onClick={() => deleteNote(index)} className="shrink-0 text-xs font-medium text-yellow-700 hover:text-yellow-900">Delete</button>
                  </li>
                ))}
              </ul>
            )}
            <div className="flex gap-2">
              <textarea
                value={noteDraft}
                onChange={event => setNoteDraft(event.target.value)}
                placeholder="Add an internal handler note..."
                rows={2}
                className="min-w-0 flex-1 resize-y rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <button
                onClick={addNote}
                disabled={!noteDraft.trim() || noteSaving}
                className="self-end rounded-lg bg-[#004fb6] px-3 py-2 text-sm font-medium text-white hover:bg-blue-800 disabled:opacity-40"
              >
                Add note
              </button>
            </div>
          </section>

          <section>
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <h3 className="text-xs font-bold uppercase tracking-wider text-gray-400">Suggested text</h3>
                <p className="mt-1 text-xs text-gray-400">Drafts require review and approval. Nothing is sent automatically.</p>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => generateDraft('external_reply')}
                  disabled={draftLoading}
                  className="rounded-lg border border-blue-200 px-3 py-2 text-xs font-medium text-blue-700 hover:bg-blue-50 disabled:opacity-40"
                >
                  Draft reply
                </button>
                <button
                  onClick={() => generateDraft('internal_note')}
                  disabled={draftLoading}
                  className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-40"
                >
                  Draft note
                </button>
              </div>
            </div>
            {replyDrafts.length > 0 && (
              <div className="space-y-3">
                {replyDrafts.map(draft => (
                  <div key={draft.draft_id} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                    <div className="mb-2 flex items-center justify-between gap-2">
                      <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                        {draft.draft_type === 'external_reply' ? 'External reply' : 'Internal note'}
                      </span>
                      <span className={`text-xs font-medium ${draft.status === 'approved' ? 'text-emerald-700' : 'text-amber-700'}`}>
                        {draft.status}
                      </span>
                    </div>
                    <textarea
                      value={draft.body}
                      onChange={event => setReplyDrafts(previous => previous.map(item => item.draft_id === draft.draft_id ? { ...item, body: event.target.value } : item))}
                      rows={4}
                      className="w-full resize-y rounded border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                    <div className="mt-2 flex justify-end gap-2">
                      <button onClick={() => updateDraft(draft.draft_id, { body: draft.body })} className="text-xs font-medium text-blue-700 hover:text-blue-900">Save edits</button>
                      {draft.status === 'pending' && (
                        <button onClick={() => updateDraft(draft.draft_id, { status: 'approved' })} className="rounded bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-700">Approve</button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* Metadata */}
          <section>
            <h3 className="text-xs font-bold uppercase tracking-wider text-gray-400 mb-3">Thread info</h3>
            <div className="text-sm text-gray-600 space-y-1">
              <div className="flex justify-between">
                <span>Last updated</span>
                <span className="font-medium text-gray-800">
                  {new Date(thread.last_updated).toLocaleString()}
                </span>
              </div>
              <div className="flex justify-between">
                <span>Handler</span>
                <span className="font-medium text-gray-800">{thread.handler_type}</span>
              </div>
            </div>
          </section>

          {auditEvents.length > 0 && (
            <section>
              <h3 className="text-xs font-bold uppercase tracking-wider text-gray-400 mb-3">Audit history</h3>
              <ol className="space-y-2">
                {auditEvents.map(event => (
                  <li key={event.event_id} className="border-l-2 border-slate-200 pl-3">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-sm font-medium text-slate-800">{event.step.replace('_', ' ')}</p>
                      <time className="text-xs text-slate-400" dateTime={event.occurred_at}>
                        {new Date(event.occurred_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </time>
                    </div>
                    <p className="mt-0.5 text-xs text-slate-500">
                      {event.model ?? 'Model unavailable'} · {event.prompt_version ?? 'Prompt version unavailable'}
                    </p>
                  </li>
                ))}
              </ol>
            </section>
          )}

          {/* Q&A */}
          <section>
            <h3 className="text-xs font-bold uppercase tracking-wider text-gray-400 mb-3">Ask about this thread</h3>

            {qaMessages.length > 0 && (
              <div className="space-y-3 mb-3">
                {qaMessages.map((m, i) => (
                  <div key={i} className={`rounded-lg px-3 py-2.5 text-sm ${m.role === 'user' ? 'bg-blue-50 text-blue-900 ml-6' : 'bg-slate-50 text-slate-800 mr-6 border border-slate-200'}`}>
                    {m.text}
                    {m.sources && m.sources.length > 0 && (
                      <div className="mt-2 border-t border-slate-200 pt-2 text-xs text-slate-500">
                        Sources: {m.sources.map(source => `${source.thread_id} / ${source.message_id}`).join(', ')}
                      </div>
                    )}
                  </div>
                ))}
                {qaLoading && (
                  <div className="bg-slate-50 rounded-lg px-3 py-2.5 text-sm text-slate-400 mr-6 border border-slate-200 animate-pulse">
                    Thinking...
                  </div>
                )}
              </div>
            )}

            <div className="flex gap-2">
              <input
                type="text"
                value={qaInput}
                onChange={e => setQaInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleAsk()}
                placeholder="e.g. What is the adjuster's appointment date?"
                className="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
              <button
                onClick={handleAsk}
                disabled={!qaInput.trim() || qaLoading}
                className="bg-[#004fb6] text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-800 disabled:opacity-40 transition-colors"
              >
                Ask
              </button>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}