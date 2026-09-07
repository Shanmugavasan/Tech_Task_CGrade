import { useState, useEffect } from 'react';

export interface ActionItem {
  action_id: string;
  task_description: string;
  deadline?: string;
  is_resolved: boolean;
}

export interface ExtractedEntities {
  policy_reference?: string;
  broker_name?: string;
  customer_name?: string;
  third_parties: string[];
}

export interface ThreadState {
  thread_id: string;
  handler_type: string;
  last_updated: string;
  message_count: number;
  internal_notes: string[];
  current_triage: {
    classification: string;
    classification_reasoning: string;
    classification_confidence: number;
    calibrated_confidence: number;
    priority_score: number;
    priority_level: string;
    urgency_justification: string;
    priority_confidence: number;
    extraction_confidence: number;
    classification_source: 'ai' | 'human';
    priority_source: 'ai' | 'human';
    override_reason: string;
    one_line_summary: string;
    required_actions: ActionItem[];
    entities: ExtractedEntities;
  };
}

export const useWebSocket = (url: string, handlerType: string, authenticated: boolean) => {
  const [threads, setThreads] = useState<Record<string, ThreadState>>({});
  const [isConnected, setIsConnected] = useState(false);
  const [simulationTime, setSimulationTime] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Hydrate from REST on mount (picks up threads processed before WS connected)
  useEffect(() => {
    if (!authenticated) return;
    fetch('http://localhost:8000/api/threads', { credentials: 'include', headers: { 'X-Handler-Type': handlerType } })
      .then(response => {
        if (!response.ok) throw new Error(`Thread request failed (${response.status})`);
        return response.json();
      })
      .then((data: ThreadState[]) => {
        setError(null);
        const map: Record<string, ThreadState> = {};
        data.forEach(t => { map[t.thread_id] = t; });
        setThreads(map);
      })
      .catch(() => setError('Unable to load the current workload. Check that the backend is running and your session is valid.'));
  }, [handlerType, authenticated]);

  useEffect(() => {
    if (!authenticated) return;
    let ws: WebSocket;
    let shouldReconnect = true;

    const connect = () => {
      ws = new WebSocket(url);
      ws.onopen = () => setIsConnected(true);
      ws.onclose = () => {
        setIsConnected(false);
        setError('Live updates are unavailable. The dashboard will keep trying to reconnect.');
        if (shouldReconnect) setTimeout(connect, 2000);
      };
      ws.onerror = () => setError('The live dashboard connection failed.');
      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.current_simulation_time) setSimulationTime(data.current_simulation_time);
        if (data.thread_id && data.handler_type === handlerType) {
          setThreads(prev => ({ ...prev, [data.thread_id]: data }));
        }
      };
    };

    connect();
    return () => { shouldReconnect = false; ws?.close(); };
  }, [url, handlerType, authenticated]);

  const sortedThreads = Object.values(threads)
    .sort((a, b) => b.current_triage.priority_score - a.current_triage.priority_score);

  return { threads: sortedThreads, isConnected, simulationTime, error };
};