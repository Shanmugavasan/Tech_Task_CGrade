import { playSimulation, pauseSimulation, setSimulationSpeed } from '../api/simulator';
import { useEffect, useState } from 'react';

interface Props {
  simulationTime: string | null;
  handlerType: string;
  allowedHandlerTypes: string[];
  onHandlerTypeChange: (handlerType: string) => void;
}

export default function SimulationControls({ simulationTime, handlerType, allowedHandlerTypes, onHandlerTypeChange }: Props) {
  const [currentSpeed, setCurrentSpeed] = useState<number>(1);
  const [debounceEnabled, setDebounceEnabled] = useState(true);
  const [brokerMinutes, setBrokerMinutes] = useState(5);

  useEffect(() => {
    fetch('http://localhost:8000/api/debounce-settings', { credentials: 'include' })
      .then(response => response.json())
      .then(settings => {
        setDebounceEnabled(settings.enabled);
        const broker = settings.settings.find((item: { source: string; debounce_minutes: number }) => item.source === 'Broker');
        if (broker) setBrokerMinutes(broker.debounce_minutes);
      })
      .catch(() => {});
  }, []);

  const handleSetSpeed = async (speed: number) => {
    setCurrentSpeed(speed);
    await setSimulationSpeed(speed);
  };

  const handleSetHandlerType = async (nextHandlerType: string) => {
    await fetch('http://localhost:8000/api/sim/handler-type', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ handler_type: nextHandlerType }),
    });
    onHandlerTypeChange(nextHandlerType);
  };

  const updateDebounce = async (changes: Record<string, unknown>) => {
    const response = await fetch('http://localhost:8000/api/debounce-settings', {
      method: 'PATCH',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(changes),
    });
    if (!response.ok) return;
    const settings = await response.json();
    setDebounceEnabled(settings.enabled);
    const broker = settings.settings.find((item: { source: string; debounce_minutes: number }) => item.source === 'Broker');
    if (broker) setBrokerMinutes(broker.debounce_minutes);
  };

  const applyAnalytics = async () => {
    const response = await fetch('http://localhost:8000/api/debounce-settings/apply-analytics', { method: 'POST', credentials: 'include' });
    if (!response.ok) return;
    const result = await response.json();
    setDebounceEnabled(result.settings.enabled);
    const broker = result.settings.settings.find((item: { source: string; debounce_minutes: number }) => item.source === 'Broker');
    if (broker) setBrokerMinutes(broker.debounce_minutes);
  };

  const formatSimTime = (isoString: string | null): string => {
    if (!isoString) return 'Waiting...';
    return new Date(isoString).toLocaleString([], {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div className="bg-white border-b border-gray-200 p-4 flex items-center justify-between shadow-sm">
      <div className="flex items-center space-x-3">
        <button
          onClick={playSimulation}
          className="bg-blue-600 text-white px-5 py-2 rounded-md font-medium hover:bg-blue-700 transition-colors"
        >
          ▶ Play Stream
        </button>
        <button
          onClick={pauseSimulation}
          className="bg-gray-100 text-gray-700 border border-gray-300 px-5 py-2 rounded-md font-medium hover:bg-gray-200 transition-colors"
        >
          ⏸ Pause
        </button>

        <div className="ml-4 px-3 py-1.5 bg-slate-100 rounded border border-slate-200 text-xs font-mono font-semibold text-slate-700">
          📅 Sim Time: {formatSimTime(simulationTime)}
          <span className="ml-2 text-slate-400">({currentSpeed}×)</span>
        </div>
      </div>

      <div className="flex items-center space-x-2">
        <label className="text-sm font-semibold text-gray-500" htmlFor="handler-type">Handler:</label>
        <select
          id="handler-type"
          value={handlerType}
          onChange={event => handleSetHandlerType(event.target.value)}
          className="rounded border border-gray-300 bg-white px-2 py-1 text-sm text-gray-700"
        >
          {allowedHandlerTypes.map(type => <option key={type} value={type}>{type}</option>)}
        </select>
        <label className="ml-3 flex items-center gap-1 text-xs text-gray-500" title="Wait before reprocessing follow-up messages">
          <input
            type="checkbox"
            checked={debounceEnabled}
            onChange={event => updateDebounce({ enabled: event.target.checked })}
            className="accent-blue-600"
          />
          Debounce
        </label>
        <label className="flex items-center gap-1 text-xs text-gray-500" title="Broker follow-up debounce window">
          Broker
          <input
            type="number"
            min="0"
            max="60"
            value={brokerMinutes}
            onChange={event => setBrokerMinutes(Number(event.target.value))}
            onBlur={() => updateDebounce({ source: 'Broker', debounce_minutes: brokerMinutes })}
            className="w-12 rounded border border-gray-300 px-1 py-1 text-xs"
          />m
        </label>
        <button
          onClick={applyAnalytics}
          className="rounded border border-slate-300 px-2 py-1 text-xs text-slate-600 hover:bg-slate-50"
          title="Apply debounce recommendations from observed follow-up intervals"
        >
          Apply analytics
        </button>
        <span className="text-sm font-semibold text-gray-500 uppercase tracking-wider mr-2">
          Playback Speed:
        </span>
        {[1, 10, 50, 100].map((speed) => (
          <button
            key={speed}
            onClick={() => handleSetSpeed(speed)}
            className={`px-3 py-1 border rounded text-sm font-medium transition-colors ${
              currentSpeed === speed
                ? 'bg-blue-600 text-white border-blue-600'
                : 'border-gray-300 text-gray-600 hover:bg-blue-50 hover:text-blue-600 hover:border-blue-300'
            }`}
          >
            {speed}x
          </button>
        ))}
      </div>
    </div>
  );
}