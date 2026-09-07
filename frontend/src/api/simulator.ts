const API_BASE = 'http://localhost:8000/api/sim';

export const playSimulation = async () => {
  await fetch(`${API_BASE}/play`, { method: 'POST', credentials: 'include' });
};

export const pauseSimulation = async () => {
  await fetch(`${API_BASE}/pause`, { method: 'POST', credentials: 'include' });
};

export const setSimulationSpeed = async (multiplier: number) => {
  await fetch(`${API_BASE}/speed`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ multiplier }),
  });
};