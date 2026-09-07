import { useState } from 'react';
import { useWebSocket } from './hooks/useWebSocket';
import SimulationControls from './components/SimulationControls';
import HandlerDashboard from './components/HandlerDashboard';
import LoginScreen from './components/LoginScreen';
import OperationsDashboard from './components/OperationsDashboard';

function App() {
  const [user, setUser] = useState<{ user_id: string; role: string; handler_types: string[] } | null>(null);
  const [handlerType, setHandlerType] = useState('Claims');
  const [showOperations, setShowOperations] = useState(false);
  const { threads, isConnected, simulationTime, error } = useWebSocket('ws://localhost:8000/ws/dashboard', handlerType, Boolean(user));

  if (!user) return <LoginScreen onLogin={nextUser => { setUser(nextUser); setHandlerType(nextUser.handler_types[0] ?? 'Claims'); }} />;

  return (
    <div className="min-h-screen font-sans text-gray-900 bg-gray-50">
      
      {/* Top Navigation Bar */}
      <header className="bg-[#004fb6] text-white p-4 shadow-md flex justify-between items-center">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-yellow-400 rounded"></div> {/* Placeholder Aviva Logo */}
          <h1 className="text-xl font-bold tracking-tight">AI Triage Engine</h1>
        </div>
        
        <div className="flex items-center gap-2 bg-blue-800 px-3 py-1.5 rounded-full border border-blue-700">
          <div className={`w-2.5 h-2.5 rounded-full shadow-inner ${isConnected ? 'bg-green-400 shadow-green-200' : 'bg-red-500 shadow-red-200'}`}></div>
          <span className="text-xs font-semibold uppercase tracking-wider text-blue-100">
            {isConnected ? 'System Live' : 'Disconnected'}
          </span>
        </div>
        {['supervisor', 'auditor', 'admin', 'platform_admin'].includes(user.role) && (
          <button onClick={() => setShowOperations(value => !value)} className="ml-3 rounded-lg border border-blue-300 px-3 py-1.5 text-xs font-medium hover:bg-blue-700">
            {showOperations ? 'Workload' : 'Operations'}
          </button>
        )}
      </header>
      
      {!showOperations && <SimulationControls
        simulationTime={simulationTime}
        handlerType={handlerType}
        allowedHandlerTypes={user.handler_types}
        onHandlerTypeChange={setHandlerType}
      />}
      {error && (
        <div className="mx-auto max-w-5xl px-6 pt-4">
          <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
            {error}
          </div>
        </div>
      )}
      
      {/* Main Content Area */}
      <main className="max-w-5xl mx-auto w-full pb-12">
        {showOperations ? <OperationsDashboard onBack={() => setShowOperations(false)} /> : <HandlerDashboard threads={threads} />}
      </main>

    </div>
  );
}

export default App;