import LiveChart from '../../components/charts/LiveChart';

export default function LiveDesk() {
  return (
    <div className="h-full flex flex-col gap-3">
      {/* Header row */}
      <div className="flex items-center justify-between shrink-0">
        <div>
          <h1 className="text-sm font-semibold text-gray-200">Live Desk</h1>
          <p className="text-[11px] text-gray-600 mt-0.5">
            NSE_INDEX · Nifty 50 · 1m
          </p>
        </div>
      </div>

      {/* Chart — flex-1 so it fills remaining height */}
      <div className="flex-1 rounded border border-gray-800 overflow-hidden min-h-0">
        <LiveChart />
      </div>
    </div>
  );
}
