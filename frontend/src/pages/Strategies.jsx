import React, { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import api, { fmtMoney, plClass } from "@/lib/api";
import { PageHeader } from "@/components/Shared";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Plus, Copy, Pause, Play, Trash2, Send } from "lucide-react";
import { toast } from "sonner";

const PLATFORMS = [
  { id: "telegram", label: "Telegram" },
  { id: "discord", label: "Discord" },
  { id: "whatsapp", label: "WhatsApp" },
];

const EMPTY = {
  name: "", description: "", asset_type: "stock", approval_mode: "auto_execute",
  auto_approve_seconds: 30, message_template: "{action} {symbol} @ {price} (qty {quantity})",
  notify_platforms: [], active: true,
  order_defaults: { order_type: "market", quantity: 1, stop_loss_pct: null, take_profit_pct: null },
};

export default function Strategies() {
  const nav = useNavigate();
  const [list, setList] = useState([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY);

  const load = useCallback(async () => {
    const { data } = await api.get("/strategies");
    setList(data);
  }, []);
  useEffect(() => { load(); }, [load]);

  const openNew = () => { setEditing(null); setForm(EMPTY); setOpen(true); };
  const openEdit = (s) => {
    setEditing(s.id);
    setForm({ ...EMPTY, ...s, order_defaults: { ...EMPTY.order_defaults, ...(s.order_defaults || {}) } });
    setOpen(true);
  };

  const save = async () => {
    if (!form.name.trim()) return toast.error("Name is required");
    const payload = { ...form, auto_approve_seconds: Number(form.auto_approve_seconds) || 30 };
    try {
      if (editing) await api.put(`/strategies/${editing}`, payload);
      else await api.post("/strategies", payload);
      toast.success(editing ? "Strategy updated" : "Strategy created");
      setOpen(false);
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed");
    }
  };

  const toggle = async (s, e) => {
    e.stopPropagation();
    await api.post(`/strategies/${s.id}/toggle`);
    load();
  };
  const del = async (s, e) => {
    e.stopPropagation();
    if (!window.confirm(`Delete "${s.name}"?`)) return;
    await api.delete(`/strategies/${s.id}`);
    toast.success("Deleted");
    load();
  };
  const copyUrl = (url, e) => {
    e.stopPropagation();
    navigator.clipboard.writeText(url);
    toast.success("Webhook URL copied");
  };

  const togglePlatform = (p) => {
    setForm((f) => ({
      ...f,
      notify_platforms: f.notify_platforms.includes(p)
        ? f.notify_platforms.filter((x) => x !== p)
        : [...f.notify_platforms, p],
    }));
  };

  return (
    <div className="fade-in">
      <PageHeader title="Strategies" subtitle="Configure webhook endpoints, approval flows & notifications">
        <Button onClick={openNew} className="bg-[#007AFF] hover:bg-[#3395FF] text-white" data-testid="new-strategy-btn">
          <Plus className="w-4 h-4 mr-2" /> New Strategy
        </Button>
      </PageHeader>

      <div className="p-8 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5" data-testid="strategy-grid">
        {list.map((s) => (
          <div key={s.id} onClick={() => nav(`/strategies/${s.id}`)}
            className="bg-card border border-border rounded-md p-5 cursor-pointer transition-all duration-200 hover:-translate-y-0.5 hover:border-white/25"
            data-testid="strategy-card-item">
            <div className="flex items-start justify-between mb-3">
              <div>
                <h3 className="font-heading font-bold text-xl leading-none">{s.name}</h3>
                <p className="text-xs text-muted-foreground mt-1 line-clamp-1">{s.description || "No description"}</p>
              </div>
              <Badge className={s.active ? "bg-[#10B981]/15 text-[#10B981]" : "bg-muted text-muted-foreground"}>
                {s.active ? "ACTIVE" : "PAUSED"}
              </Badge>
            </div>
            <div className="flex gap-2 mb-4 flex-wrap">
              <Badge variant="outline" className="text-xs uppercase">{s.asset_type}</Badge>
              <Badge variant="outline" className="text-xs">{s.approval_mode.replace(/_/g, " ")}</Badge>
              {s.notify_platforms?.map((p) => <Badge key={p} variant="outline" className="text-xs capitalize">{p}</Badge>)}
            </div>
            <div className="grid grid-cols-3 gap-2 mb-4 text-center">
              <div>
                <div className="text-xs text-muted-foreground uppercase tracking-wide">P&L</div>
                <div className={`font-mono font-bold ${plClass(s.total_pnl)}`}>{fmtMoney(s.total_pnl)}</div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground uppercase tracking-wide">Win</div>
                <div className="font-mono font-bold">{s.win_rate}%</div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground uppercase tracking-wide">Trades</div>
                <div className="font-mono font-bold">{s.total_trades}</div>
              </div>
            </div>
            <div className="flex items-center gap-2 mb-3 bg-background border border-border rounded px-2 py-1.5">
              <code className="text-xs text-muted-foreground truncate flex-1">{s.webhook_url}</code>
              <button onClick={(e) => copyUrl(s.webhook_url, e)} className="text-muted-foreground hover:text-foreground" data-testid={`copy-webhook-${s.id}`}>
                <Copy className="w-3.5 h-3.5" />
              </button>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" className="flex-1" onClick={(e) => toggle(s, e)} data-testid={`toggle-${s.id}`}>
                {s.active ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
              </Button>
              <Button variant="outline" size="sm" className="flex-1" onClick={(e) => { e.stopPropagation(); openEdit(s); }}>
                Edit
              </Button>
              <Button variant="outline" size="sm" onClick={(e) => del(s, e)} className="text-[#EF4444]" data-testid={`delete-${s.id}`}>
                <Trash2 className="w-3.5 h-3.5" />
              </Button>
            </div>
          </div>
        ))}
        {list.length === 0 && (
          <div className="col-span-full text-center py-16 text-muted-foreground">
            No strategies yet. Create your first one.
          </div>
        )}
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto" data-testid="strategy-dialog">
          <DialogHeader><DialogTitle>{editing ? "Edit Strategy" : "New Strategy"}</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div>
              <Label className="text-xs">Name</Label>
              <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="strategy-name-input" />
            </div>
            <div>
              <Label className="text-xs">Description</Label>
              <Textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} rows={2} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">Asset Type</Label>
                <Select value={form.asset_type} onValueChange={(v) => setForm({ ...form, asset_type: v })}>
                  <SelectTrigger data-testid="asset-type-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="stock">Stock</SelectItem>
                    <SelectItem value="option">Option</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs">Approval Mode</Label>
                <Select value={form.approval_mode} onValueChange={(v) => setForm({ ...form, approval_mode: v })}>
                  <SelectTrigger data-testid="approval-mode-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="auto_execute">Auto-execute</SelectItem>
                    <SelectItem value="require_approval">Require approval</SelectItem>
                    <SelectItem value="auto_approve_timer">Auto-approve timer</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            {form.approval_mode === "auto_approve_timer" && (
              <div>
                <Label className="text-xs">Auto-approve after (seconds)</Label>
                <Input type="number" value={form.auto_approve_seconds}
                  onChange={(e) => setForm({ ...form, auto_approve_seconds: e.target.value })} />
              </div>
            )}
            <div>
              <Label className="text-xs">Message Template</Label>
              <Input value={form.message_template} onChange={(e) => setForm({ ...form, message_template: e.target.value })} />
              <p className="text-xs text-muted-foreground mt-1">Variables: {"{symbol} {action} {price} {quantity} {order_type}"}</p>
            </div>
            <div>
              <Label className="text-xs">Notification Platforms</Label>
              <div className="flex gap-2 mt-2">
                {PLATFORMS.map((p) => (
                  <button key={p.id} type="button" onClick={() => togglePlatform(p.id)}
                    data-testid={`platform-${p.id}`}
                    className={`px-3 py-1.5 rounded-md text-sm border transition-all ${
                      form.notify_platforms.includes(p.id)
                        ? "bg-[#007AFF] text-white border-[#007AFF]"
                        : "border-border text-muted-foreground hover:border-white/30"
                    }`}>
                    {p.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">Default Order Type</Label>
                <Select value={form.order_defaults.order_type}
                  onValueChange={(v) => setForm({ ...form, order_defaults: { ...form.order_defaults, order_type: v } })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="market">Market</SelectItem>
                    <SelectItem value="limit">Limit</SelectItem>
                    <SelectItem value="stop">Stop</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs">Default Quantity</Label>
                <Input type="number" value={form.order_defaults.quantity}
                  onChange={(e) => setForm({ ...form, order_defaults: { ...form.order_defaults, quantity: Number(e.target.value) } })} />
              </div>
            </div>
            <div className="flex items-center justify-between">
              <Label className="text-xs">Active</Label>
              <Switch checked={form.active} onCheckedChange={(v) => setForm({ ...form, active: v })} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={save} className="bg-[#007AFF] hover:bg-[#3395FF] text-white" data-testid="save-strategy-btn">
              <Send className="w-4 h-4 mr-2" /> {editing ? "Update" : "Create"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
