import { useEffect, useState, type FormEvent } from 'react';

interface DemoUser {
  username: string;
  password: string;
  role: string;
  handler_types: string[];
}

interface AuthUser {
  user_id: string;
  role: string;
  handler_types: string[];
}

interface Props {
  onLogin: (user: AuthUser) => void;
}

export default function LoginScreen({ onLogin }: Props) {
  const [users, setUsers] = useState<DemoUser[]>([]);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    fetch('http://localhost:8000/api/auth/demo-users', { credentials: 'include' })
      .then(response => response.ok ? response.json() : [])
      .then((demoUsers: DemoUser[]) => {
        setUsers(demoUsers);
        if (demoUsers[0]) {
          setUsername(demoUsers[0].username);
          setPassword(demoUsers[0].password);
        }
      })
      .catch(() => setError('The authentication service is unavailable.'));
  }, []);

  const selectUser = (nextUsername: string) => {
    const user = users.find(candidate => candidate.username === nextUsername);
    setUsername(nextUsername);
    setPassword(user?.password ?? '');
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError('');
    const response = await fetch('http://localhost:8000/api/auth/login', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    if (!response.ok) {
      setError('Invalid username or password.');
      return;
    }
    onLogin(await response.json());
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-100 px-4">
      <form onSubmit={submit} className="w-full max-w-sm rounded-xl border border-slate-200 bg-white p-7 shadow-lg">
        <div className="mb-6">
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-blue-600">Aviva operations</p>
          <h1 className="mt-2 text-2xl font-semibold text-slate-900">AI Triage Engine</h1>
          <p className="mt-2 text-sm text-slate-500">Sign in to view your department workload.</p>
        </div>
        <label className="block text-sm font-medium text-slate-700" htmlFor="username">User</label>
        <select id="username" value={username} onChange={event => selectUser(event.target.value)} className="mt-1 mb-4 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm">
          {users.map(user => <option key={user.username} value={user.username}>{user.username} · {user.role}</option>)}
        </select>
        <label className="block text-sm font-medium text-slate-700" htmlFor="password">Password</label>
        <input id="password" type="password" value={password} onChange={event => setPassword(event.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
        {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
        <button type="submit" disabled={!username || !password} className="mt-5 w-full rounded-lg bg-[#004fb6] px-4 py-2.5 text-sm font-medium text-white hover:bg-blue-800 disabled:opacity-40">Sign in</button>
        <p className="mt-4 text-xs text-slate-400">Demo accounts and passwords are prefilled for local evaluation only.</p>
      </form>
    </main>
  );
}
