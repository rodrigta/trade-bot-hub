import React, { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api, { fmtMoney, plClass } from "@/lib/api";
import { PageHeader } from "@/components/Shared";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { StatusBadge } from "@/pages/Dashboard";
import { ArrowLeft, Copy } from "lucide-react";
import { toast } from "sonner";

export default function StrategyDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const [s, setS] = useState(null);

  useEffect(() => { api.get(`/strategies/${id}`).then((r) => setS(r.data)); }, [id]);
  if (!s) return <div className="p-8 text-muted-foreground">Loading…</div>;

  return (
    <div className="fade-in">
      <PageHeader title={s.name} subtitle={s.description || "Strategy detail"}>
        <Button variant="outline" onClick={() => nav("/strategies")}><ArrowLeft className="w-4 h-4 mr-2" /> Back</Button>
      </PageHeader>
      <div className="p-8 space-y-6">
        <div className="bg-card border border-border rounded-md p-5">
          <h3 className="font-heading font-bold text-lg mb-4">Configuration</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <Field label="Asset Type" value={s.asset_type} />
            <Field label="Approval Mode" value={s.approval_mode.replace(/_/g, " ")} />
            <Field label="Auto-approve" value={s.approval_mode === "auto_approve_timer" ? `${s.auto_approve_seconds}s` : "—"} />
            <Field label="Status" value={s.active ? "Active" : "Paused"} />
            <Field label="Default Order" value={s.order_defaults?.order_type} />
            <Field label="Default Qty" value={s.order_defaults?.quantity} />
            <div className="col-span-2">
              <div className="text-xs uppercase tracking-wider text-muted-foreground">Notify Platforms</div>
              <div className="flex gap-1 mt-1">
                {s.notify_platforms?.length ? s.notify_platforms.map((p) => <Badge key={p} variant="outline" className="capitalize">{p}</Badge>) : "—"}
              </div>
            </div>
          </div>
          <div className="mt-4 flex items-center gap-2 bg-background border border-border rounded px-3 py-2">
            <span className="text-xs text-muted-foreground uppercase tracking-wide">Webhook</span>
            <code className="text-xs flex-1 truncate">{s.webhook_url}</code>
            <button onClick={() => { navigator.clipboard.writeText(s.webhook_url); toast.success("Copied"); }}>
              <Copy className="w-4 h-4 text-muted-foreground hover:text-foreground" />
            </button>
          </div>
          <div className="mt-2 text-xs text-muted-foreground">Template: <code>{s.message_template}</code></div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-card border border-border rounded-md p-5">
            <h3 className="font-heading font-bold text-lg mb-3">Alert History</h3>
            <div className="space-y-2 max-h-80 overflow-y-auto">
              {s.alerts?.length ? s.alerts.map((a) => (
                <div key={a.id} className="flex items-center justify-between border-b border-border/50 py-2 text-sm">
                  <span className="font-mono font-semibold">{a.action?.toUpperCase()} {a.symbol}</span>
                  <StatusBadge status={a.status} />
                  <span className="text-xs text-muted-foreground">{new Date(a.received_at).toLocaleDateString()}</span>
                </div>
              )) : <div className="text-sm text-muted-foreground py-6 text-center">No alerts.</div>}
            </div>
          </div>
          <div className="bg-card border border-border rounded-md p-5">
            <h3 className="font-heading font-bold text-lg mb-3">Linked Trades</h3>
            <div className="space-y-2 max-h-80 overflow-y-auto">
              {s.trades?.length ? s.trades.map((t) => (
                <div key={t.id} className="flex items-center justify-between border-b border-border/50 py-2 text-sm">
                  <span className="font-mono font-semibold">{t.symbol}</span>
                  <span className="text-xs text-muted-foreground capitalize">{t.side} · {t.status}</span>
                  <span className={`font-mono font-bold ${plClass(t.pnl)}`}>{fmtMoney(t.pnl)}</span>
                </div>
              )) : <div className="text-sm text-muted-foreground py-6 text-center">No trades.</div>}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Field({ label, value }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="font-mono font-semibold capitalize mt-0.5">{value ?? "—"}</div>
    </div>
  );
}
