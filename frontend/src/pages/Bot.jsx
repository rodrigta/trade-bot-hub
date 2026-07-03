import React, { useEffect, useState, useCallback } from "react";
import api from "@/lib/api";
import { PageHeader, StatCard } from "@/components/Shared";
import { StatusBadge } from "@/pages/Dashboard";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Wifi, WifiOff, Server, Zap, PlugZap, Power } from "lucide-react";
import { toast } from "sonner";

export default function Bot() {
  const [status, setStatus] = useState(null);
  const [connecting, setConnecting] = useState(false);
  const [host, setHost] = useState("127.0.0.1");
  const [port, setPort] = useState("7497");

  const load = useCallback(async () => {
    const { data } = await api.get("/bot/status");
    setStatus(data);
    setHost(data.host || "127.0.0.1");
    setPort(String(data.port || "7497"));
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 4000);
    return () => clearInterval(id);
  }, [load]);

  const setAutoTrade = async (enabled) => {
    await api.post("/bot/auto-trade", { enabled });
    toast.success(enabled ? "Auto-Trade ENABLED" : "Auto-Trade disabled — alerts now held for manual approval");
    load();
  };

  const connectBroker = async () => {
    setConnecting(true);
    try {
      await api.post("/bot/broker", { connected: true, host, port: Number(port) });
      toast.success("Broker set to LIVE. Orders route to IBKR when the gateway is reachable.");
      load();
    } finally {
      setConnecting(false);
    }
  };

  const disconnectBroker = async () => {
    await api.post("/bot/broker", { connected: false });
    toast.success("Broker disconnected — using paper simulation");
    load();
  };

  if (!status) return <div className="p-8 text-muted-foreground">Loading…</div>;

  return (
    <div className="fade-in">
      <PageHeader title="Trading Bot" subtitle="Auto-trade control, broker connection & live alert log" />
      <div className="p-8 space-y-6">
        {/* Control row */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Auto-Trade master switch */}
          <div className="bg-card border border-border rounded-md p-5" data-testid="auto-trade-card">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Zap className={`w-5 h-5 ${status.auto_trade_enabled ? "text-[#10B981]" : "text-muted-foreground"}`} />
                <h3 className="font-heading font-bold text-lg">Auto-Trade</h3>
              </div>
              <Switch checked={status.auto_trade_enabled} onCheckedChange={setAutoTrade} data-testid="auto-trade-toggle" />
            </div>
            <p className="text-sm text-muted-foreground mt-3">
              {status.auto_trade_enabled
                ? "Signals from auto-execute strategies are placed automatically. Timed strategies auto-approve on schedule."
                : "OFF — every incoming signal is held for manual approval (notifications still sent). Turn on to let the bot place orders automatically."}
            </p>
          </div>

          {/* Broker connection */}
          <div className="bg-card border border-border rounded-md p-5" data-testid="broker-card">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                {status.broker_connected ? <Wifi className="w-5 h-5 text-[#10B981]" /> : <WifiOff className="w-5 h-5 text-muted-foreground" />}
                <h3 className="font-heading font-bold text-lg">Broker (IBKR)</h3>
              </div>
              <Badge className={status.broker_connected ? "bg-[#10B981]/15 text-[#10B981]" : "bg-muted text-muted-foreground"}>
                {status.broker_connected ? "CONNECTED / LIVE" : "NOT CONNECTED"}
              </Badge>
            </div>
            {status.broker_connected ? (
              <div className="space-y-3">
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Server className="w-4 h-4" /> <span className="font-mono">{status.host}:{status.port}</span>
                </div>
                <Button variant="outline" size="sm" onClick={disconnectBroker} data-testid="disconnect-broker-btn">
                  <Power className="w-4 h-4 mr-2" /> Disconnect broker
                </Button>
              </div>
            ) : (
              <div className="space-y-3">
                <p className="text-sm text-muted-foreground">
                  No broker connected — orders use <strong>paper simulation</strong>. Connect IBKR TWS / IB Gateway to trade live.
                </p>
                <div className="flex gap-2">
                  <div className="flex-1">
                    <Label className="text-xs">Gateway Host</Label>
                    <Input value={host} onChange={(e) => setHost(e.target.value)} data-testid="broker-host-input" />
                  </div>
                  <div className="w-28">
                    <Label className="text-xs">Port</Label>
                    <Input value={port} onChange={(e) => setPort(e.target.value)} data-testid="broker-port-input" />
                  </div>
                </div>
                <Button onClick={connectBroker} disabled={connecting}
                  className="bg-[#007AFF] hover:bg-[#3395FF] text-white" data-testid="connect-broker-btn">
                  <PlugZap className="w-4 h-4 mr-2" /> {connecting ? "Connecting…" : "Connect Broker"}
                </Button>
              </div>
            )}
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard label="Total Alerts" value={status.stats.total} />
          <StatCard label="Executed" value={<span className="text-[#10B981]">{status.stats.executed}</span>} />
          <StatCard label="Pending" value={<span className="text-[#F59E0B]">{status.stats.pending}</span>} />
          <StatCard label="Failed" value={<span className="text-[#EF4444]">{status.stats.failed}</span>} />
        </div>

        {!status.broker_connected && status.auto_trade_enabled && (
          <div className="bg-amber-500/10 border border-amber-500/30 rounded-md p-4 text-sm">
            <strong className="text-[#F59E0B]">Paper mode:</strong> Auto-Trade is ON but no broker is connected, so fills come from the built-in <strong>paper simulation engine</strong>. Connect a broker above to place live orders (requires self-hosted TWS/IB Gateway reachable from the backend).
          </div>
        )}

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
