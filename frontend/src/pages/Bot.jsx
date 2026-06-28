import React, { useEffect, useState, useCallback } from "react";
import api from "@/lib/api";
import { PageHeader, StatCard } from "@/components/Shared";
import { StatusBadge } from "@/pages/Dashboard";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Wifi, WifiOff, Server } from "lucide-react";
import { toast } from "sonner";

export default function Bot() {
  const [status, setStatus] = useState(null);

  const load = useCallback(async () => {
    const { data } = await api.get("/bot/status");
    setStatus(data);
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 4000);
    return () => clearInterval(id);
  }, [load]);

  const setMode = async (live) => {
    await api.post("/bot/mode", { live });
    toast.success(live ? "Switched to LIVE (IBKR)" : "Switched to PAPER");
    load();
  };

  if (!status) return <div className="p-8 text-muted-foreground">Loading…</div>;

  return (
    <div className="fade-in">
      <PageHeader title="Trading Bot" subtitle="IBKR connection, execution mode & live alert log" />
      <div className="p-8 space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="bg-card border border-border rounded-md p-4 flex items-center gap-3" data-testid="ibkr-status">
            {status.ibkr_connected ? <Wifi className="w-8 h-8 text-[#10B981]" /> : <WifiOff className="w-8 h-8 text-muted-foreground" />}
            <div>
              <div className="text-xs uppercase tracking-wider text-muted-foreground">IBKR</div>
              <div className="font-bold">{status.ibkr_connected ? "Connected" : "Simulated"}</div>
            </div>
          </div>
          <div className="bg-card border border-border rounded-md p-4 flex items-center gap-3">
            <Server className="w-8 h-8 text-[#007AFF]" />
            <div>
              <div className="text-xs uppercase tracking-wider text-muted-foreground">Gateway</div>
              <div className="font-mono text-sm">{status.host}:{status.port}</div>
            </div>
          </div>
          <StatCard label="Total Alerts" value={status.stats.total} />
          <div className="bg-card border border-border rounded-md p-4">
            <div className="text-xs uppercase tracking-wider text-muted-foreground mb-2">Execution Mode</div>
            <div className="flex items-center gap-3">
              <span className={`text-sm font-bold ${status.mode === "paper" ? "text-[#F59E0B]" : "text-muted-foreground"}`}>PAPER</span>
              <Switch checked={status.mode === "live"} onCheckedChange={setMode} data-testid="mode-toggle" />
              <span className={`text-sm font-bold ${status.mode === "live" ? "text-[#10B981]" : "text-muted-foreground"}`}>LIVE</span>
            </div>
          </div>
        </div>

        <div className="bg-amber-500/10 border border-amber-500/30 rounded-md p-4 text-sm">
          <strong className="text-[#F59E0B]">Note:</strong> Live IBKR execution requires TWS / IB Gateway running on your self-hosted machine.
          In this cloud environment orders are filled by the built-in <strong>paper simulation engine</strong>. Configure your gateway host/port under Notifications → Settings.
        </div>

        <div className="bg-card border border-border rounded-md p-5">
          <h3 className="font-heading font-bold text-lg mb-4">Execution Log</h3>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs uppercase tracking-wider text-muted-foreground border-b border-border">
                <th className="text-left py-2">Symbol</th>
                <th className="text-left py-2">Action</th>
                <th className="text-left py-2">Strategy</th>
                <th className="text-right py-2">Qty</th>
                <th className="text-left py-2 pl-4">Status</th>
                <th className="text-right py-2">Received</th>
              </tr>
            </thead>
            <tbody>
              {status.recent_alerts.map((a) => (
                <tr key={a.id} className="border-b border-border/50 hover:bg-accent/50">
                  <td className="py-2 font-mono font-semibold">{a.symbol}</td>
                  <td className={a.action === "buy" ? "text-[#10B981]" : "text-[#EF4444]"}>{a.action?.toUpperCase()}</td>
                  <td className="text-muted-foreground">{a.strategy_name}</td>
                  <td className="text-right font-mono">{a.quantity}</td>
                  <td className="pl-4"><StatusBadge status={a.status} /></td>
                  <td className="text-right font-mono text-xs text-muted-foreground">{new Date(a.received_at).toLocaleString()}</td>
                </tr>
              ))}
              {status.recent_alerts.length === 0 && <tr><td colSpan={6} className="py-8 text-center text-muted-foreground">No alerts received yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
