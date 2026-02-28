import { Outlet, NavLink } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';

export default function DashboardLayout() {
  const { user, logout } = useAuth();

  return (
    <div className="h-screen flex flex-col bg-[#0a0e17] text-gray-200 overflow-hidden">
      {/* Top Bar */}
      <header className="h-12 flex items-center justify-between px-4 bg-[#0d1321] border-b border-gray-800 shrink-0">
        <div className="flex items-center gap-6">
          <span className="text-sm font-bold tracking-wide text-emerald-400">
            PRICE ACTION
          </span>
          <nav className="flex gap-1">
            <NavLink
              to="/dashboard"
              end
              className={({ isActive }) =>
                `px-3 py-1.5 text-xs rounded transition-colors ${
                  isActive
                    ? 'bg-gray-800 text-white'
                    : 'text-gray-400 hover:text-gray-200'
                }`
              }
            >
              Live Desk
            </NavLink>
            <NavLink
              to="/dashboard/paper-trading"
              className={({ isActive }) =>
                `px-3 py-1.5 text-xs rounded transition-colors ${
                  isActive
                    ? 'bg-gray-800 text-white'
                    : 'text-gray-400 hover:text-gray-200'
                }`
              }
            >
              Paper Trading
            </NavLink>
          </nav>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-xs text-gray-500">{user?.username}</span>
          <button
            onClick={logout}
            className="text-xs text-gray-500 hover:text-red-400 transition-colors cursor-pointer"
          >
            Logout
          </button>
        </div>
      </header>

      {/* 3-Panel Grid */}
      <div className="flex-1 grid grid-cols-[240px_1fr_280px] min-h-0">
        {/* Left Sidebar — Watchlist */}
        <aside className="bg-[#0d1321] border-r border-gray-800 overflow-y-auto p-3">
          <h2 className="text-[10px] font-semibold uppercase tracking-widest text-gray-500 mb-3">
            Watchlist
          </h2>
          <div className="space-y-1">
            {['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'META'].map(
              (ticker) => (
                <div
                  key={ticker}
                  className="flex items-center justify-between px-2 py-1.5 rounded text-xs hover:bg-gray-800/50 cursor-pointer transition-colors"
                >
                  <span className="font-medium text-gray-300">{ticker}</span>
                  <span className="text-gray-600">—</span>
                </div>
              )
            )}
          </div>
        </aside>

        {/* Center Canvas */}
        <main className="overflow-hidden p-4 flex flex-col min-h-0">
          <Outlet />
        </main>

        {/* Right Sidebar — AI Logs */}
        <aside className="bg-[#0d1321] border-l border-gray-800 overflow-y-auto p-3">
          <h2 className="text-[10px] font-semibold uppercase tracking-widest text-gray-500 mb-3">
            AI Signal Log
          </h2>
          <div className="text-xs text-gray-600 italic">
            No signals yet. Connect a data feed to begin.
          </div>
        </aside>
      </div>
    </div>
  );
}
