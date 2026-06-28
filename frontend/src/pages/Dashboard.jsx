import React, { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import api, { fmtMoney, fmtNum, plClass } from "@/lib/api";
import { PageHeader, StatCard } from "@/components/Shared";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid,
} from "recharts";
import { Check, X, Clock, TrendingUp, Activity, Zap } from "lucide-react";
import { toast } from "sonner";

function Countdown({ target }) {
  const [left, setLeft] = useState(0);
  useEffect(() => {
    if (!target) return;
    const tick = () => setLeft(Math.max(0, Math.round((new Date(target) - new Date()) / 1000)));
    tick();
    const id = setInterval(tick, 500);
    return () => clearInterval(id);
  }, [target]);
  if (!target) return null;
  return (
    <span className={`font-mono font-bold ${left <= 10 ? "text-[#EF4444] pulse-urgent" : "text-[#F59E0B]"}`}>
      {left}s
    </span>
  );
}

export default function Dashboard() {
  const nav = useNavigate();
  const [ov, setOv] = useState(null);
  const [eq, setEq] = useState([]);
  const [pending, setPending] = useState([]);
  const [alerts, setAlerts] = useState([]);

  const load = useCallback(async () => {
    const [o, e, p, a] = await Promise.all([
      api.get("/analytics/overview"),
      api.get("/analytics/equity-curve"),
      api.get("/alerts/pending"),
      api.get("/alerts"),
    ]);
    setOv(o.data); setEq(e.data.points); setPending(p.data); setAlerts(a.data.slice(0, 8));
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [load]);

  const act = async (id, action) => {
    try {
      await api.post(`/alerts/${id}/${action}`);
      toast.success(`Alert ${action}d`);
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed");
    }
  };

  return (
    <div className="fade-in">
      <PageHeader title="Dashboard" subtitle="Performance overview & live approvals">
        <Button onClick={() => nav("/journal")} className="bg-[#007AFF] hover:bg-[#3395FF] text-white" data-testid="log-trade-btn">
          <TrendingUp className="w-4 h-4 mr-2" /> Journal
        </Button>
      </PageHeader>

      <div className="p-8 space-y-6">
        {ov && (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
            <StatCard testId="stat-total-pnl" label="Total P&L"
              value={<span className={plClass(ov.total_pnl)}>{fmtMoney(ov.total_pnl)}</span>}
              sub={`${ov.total_trades} trades`} />
            <StatCard label="Win Rate" value={`${ov.win_rate}%`} sub={`${ov.wins}W / ${ov.losses}L`} />
            <StatCard label="Profit Factor" value={fmtNum(ov.profit_factor)} sub={`Expectancy ${ov.expectancy}R`} />
            <StatCard label="Avg Win" value={<span className="text-[#10B981]">{fmtMoney(ov.avg_win)}</span>}
              sub={<span className="text-[#EF4444]">{fmtMoney(ov.avg_loss)} avg loss</span>} />
            <StatCard label="Current Streak"
              value={<span className={ov.current_streak >= 0 ? "text-[#10B981]" : "text-[#EF4444]"}>{ov.current_streak > 0 ? `+${ov.current_streak}` : ov.current_streak}</span>}
              sub={`Best +${ov.best_streak} / ${ov.worst_streak}`} />
            <StatCard label="Open Positions" value={ov.open_positions} sub="live" />
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 bg-card border border-border rounded-md p-5">
            <div className="flex items-center gap-2 mb-4">
              <Activity className="w-4 h-4 text-[#007AFF]" />
              <h3 className="font-heading font-bold text-lg">Cumulative Equity</h3>
            </div>
            <ResponsiveContainer width="100%" height={280}>
              <AreaChart data={eq}>
                <defs>
                  <linearGradient id="eqg" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#007AFF" stopOpacity={0.4} />
                    <stop offset="100%" stopColor="#007AFF" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                <XAxis dataKey="i" tick={{ fontSize: 11, fill: "#71717A" }} />
                <YAxis tick={{ fontSize: 11, fill: "#71717A" }} tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} />
                <Tooltip
                  contentStyle={{ background: "#141414", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 6, fontSize: 12 }}
                  formatter={(v) => fmtMoney(v)} />
                <Area type="monotone" dataKey="cumulative" stroke="#007AFF" strokeWidth={2} fill="url(#eqg)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-card border border-border rounded-md p-5" data-testid="approval-center">
            <div className="flex items-center gap-2 mb-4">
              <Zap className="w-4 h-4 text-[#F59E0B]" />
              <h3 className="font-heading font-bold text-lg">Approval Center</h3>
              {pending.length > 0 && <Badge className="bg-[#F59E0B] text-black">{pending.length}</Badge>}
            </div>
            <div className="space-y-3 max-h-[280px] overflow-y-auto">
              {pending.length === 0 && (
                <div className="text-sm text-muted-foreground py-8 text-center">No pending approvals.</div>
              )}
              {pending.map((a) => (
                <div key={a.id} className="border border-border rounded-md p-3 bg-background" data-testid={`pending-alert-${a.id}`}>
                  <div className="flex items-center justify-between mb-1">
                    <div className="font-mono font-bold">
                      <span className={a.action === "buy" ? "text-[#10B981]" : "text-[#EF4444]"}>{a.action?.toUpperCase()}</span> {a.symbol}
                    </div>
                    {a.auto_approve_at ? <Countdown target={a.auto_approve_at} /> : <Clock className="w-4 h-4 text-muted-foreground" />}
                  </div>
                  <div className="text-xs text-muted-foreground mb-2">
                    {a.strategy_name} · qty {a.quantity} · {a.order_type}
                  </div>
                  <div className="flex gap-2">
                    <Button size="sm" onClick={() => act(a.id, "approve")}
                      className="flex-1 bg-[#10B981] hover:bg-[#10B981]/80 text-white h-8" data-testid={`approve-${a.id}`}>
                      <Check className="w-4 h-4 mr-1" /> Approve
                    </Button>
                    <Button size="sm" onClick={() => act(a.id, "reject")}
                      className="flex-1 bg-[#EF4444] hover:bg-[#EF4444]/80 text-white h-8" data-testid={`reject-${a.id}`}>
                      <X className="w-4 h-4 mr-1" /> Reject
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="bg-card border border-border rounded-md p-5">
          <h3 className="font-heading font-bold text-lg mb-4">Recent Alerts</h3>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs uppercase tracking-wider text-muted-foreground border-b border-border">
                <th className="text-left py-2 font-semibold">Symbol</th>
                <th className="text-left py-2 font-semibold">Action</th>
                <th className="text-left py-2 font-semibold">Strategy</th>
                <th className="text-right py-2 font-semibold">Qty</th>
                <th className="text-left py-2 font-semibold pl-4">Status</th>
                <th className="text-right py-2 font-semibold">Time</th>
              </tr>
            </thead>
            <tbody>
              {alerts.map((a) => (
                <tr key={a.id} className="border-b border-border/50 hover:bg-accent/50">
                  <td className="py-2 font-mono font-semibold">{a.symbol}</td>
                  <td className={a.action === "buy" ? "text-[#10B981]" : "text-[#EF4444]"}>{a.action?.toUpperCase()}</td>
                  <td className="text-muted-foreground">{a.strategy_name}</td>
                  <td className="text-right font-mono">{a.quantity}</td>
                  <td className="pl-4"><StatusBadge status={a.status} /></td>
                  <td className="text-right font-mono text-xs text-muted-foreground">{new Date(a.received_at).toLocaleString()}</td>
                </tr>
              ))}
              {alerts.length === 0 && <tr><td colSpan={6} className="py-8 text-center text-muted-foreground">No alerts yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export function StatusBadge({ status }) {
  const map = {
    executed: "bg-[#10B981]/15 text-[#10B981]",
    approved: "bg-[#10B981]/15 text-[#10B981]",
    pending: "bg-[#F59E0B]/15 text-[#F59E0B]",
    rejected: "bg-[#EF4444]/15 text-[#EF4444]",
    received: "bg-[#3B82F6]/15 text-[#3B82F6]",
    ignored_paused: "bg-muted text-muted-foreground",
  };
  return <span className={`px-2 py-0.5 rounded text-xs font-semibold uppercase tracking-wide ${map[status] || "bg-muted text-muted-foreground"}`}>{(status || "").replace("_", " ")}</span>;
}
