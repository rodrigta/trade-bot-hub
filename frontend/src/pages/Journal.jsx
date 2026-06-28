import React, { useEffect, useState, useCallback } from "react";
import api, { fmtMoney, fmtNum, plClass } from "@/lib/api";
import { PageHeader } from "@/components/Shared";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Plus, Filter, Trash2, Upload, X } from "lucide-react";
import { toast } from "sonner";

const EMPTY = {
  symbol: "", side: "long", asset_type: "stock", entry_price: "", exit_price: "",
  quantity: 1, fees: 0, status: "closed", strategy_id: "", tags: [], notes: "",
  risk_amount: "", mfe: "", mae: "", option_expiry: "", option_strike: "", option_right: "call",
  account: "paper",
};

export default function Journal() {
  const [trades, setTrades] = useState([]);
  const [strategies, setStrategies] = useState([]);
  const [tags, setTags] = useState([]);
  const [filters, setFilters] = useState({ symbol: "", side: "", strategy_id: "", tag: "", start: "", end: "" });
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [detail, setDetail] = useState(null);

  const load = useCallback(async () => {
    const params = {};
    Object.entries(filters).forEach(([k, v]) => { if (v) params[k] = v; });
    const [t, s, g] = await Promise.all([
      api.get("/trades", { params }),
      api.get("/strategies"),
      api.get("/tags"),
    ]);
    setTrades(t.data); setStrategies(s.data); setTags(g.data);
  }, [filters]);
  useEffect(() => { load(); }, [load]);

  const stratName = (id) => strategies.find((s) => s.id === id)?.name || "—";

  const openNew = () => { setEditing(null); setForm(EMPTY); setOpen(true); };
  const openEdit = (t) => {
    setEditing(t.id);
    setForm({ ...EMPTY, ...t, entry_price: t.entry_price ?? "", exit_price: t.exit_price ?? "",
      risk_amount: t.risk_amount ?? "", mfe: t.mfe ?? "", mae: t.mae ?? "", strategy_id: t.strategy_id || "" });
    setDetail(null);
    setOpen(true);
  };

  const save = async () => {
    if (!form.symbol.trim() || form.entry_price === "") return toast.error("Symbol and entry price required");
    const num = (v) => (v === "" || v === null ? null : Number(v));
    const payload = {
      ...form, symbol: form.symbol.toUpperCase(),
      entry_price: num(form.entry_price), exit_price: num(form.exit_price),
      quantity: Number(form.quantity), fees: Number(form.fees) || 0,
      risk_amount: num(form.risk_amount), mfe: num(form.mfe), mae: num(form.mae),
      option_strike: form.asset_type === "option" ? num(form.option_strike) : null,
      option_expiry: form.asset_type === "option" ? (form.option_expiry || null) : null,
      option_right: form.asset_type === "option" ? form.option_right : null,
      strategy_id: form.strategy_id || null,
    };
    try {
      if (editing) await api.put(`/trades/${editing}`, payload);
      else await api.post("/trades", payload);
      toast.success(editing ? "Trade updated" : "Trade added");
      setOpen(false);
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed");
    }
  };

  const del = async (id) => {
    if (!window.confirm("Delete this trade?")) return;
    await api.delete(`/trades/${id}`);
    toast.success("Deleted");
    load();
  };

  const toggleTag = (name) => {
    setForm((f) => ({ ...f, tags: f.tags.includes(name) ? f.tags.filter((t) => t !== name) : [...f.tags, name] }));
  };

  const uploadShot = async (e) => {
    const file = e.target.files?.[0];
    if (!file || !detail) return;
    const fd = new FormData();
    fd.append("file", file);
    const { data } = await api.post(`/trades/${detail.id}/attachment`, fd);
    toast.success("Screenshot uploaded");
    setDetail({ ...detail, screenshot_url: data.url });
    load();
  };

  const tagColor = (name) => tags.find((t) => t.name === name)?.color || "#007AFF";

  return (
    <div className="fade-in">
      <PageHeader title="Trade Journal" subtitle={`${trades.length} trades`}>
        <Button onClick={openNew} className="bg-[#007AFF] hover:bg-[#3395FF] text-white" data-testid="add-trade-btn">
          <Plus className="w-4 h-4 mr-2" /> Add Trade
        </Button>
      </PageHeader>

      <div className="p-8 space-y-4">
        <div className="bg-card border border-border rounded-md p-4 flex flex-wrap items-end gap-3" data-testid="journal-filters">
          <Filter className="w-4 h-4 text-muted-foreground mb-2" />
          <div>
            <Label className="text-xs">Symbol</Label>
            <Input className="h-9 w-28" value={filters.symbol} onChange={(e) => setFilters({ ...filters, symbol: e.target.value })} />
          </div>
          <div>
            <Label className="text-xs">Side</Label>
            <Select value={filters.side || "all"} onValueChange={(v) => setFilters({ ...filters, side: v === "all" ? "" : v })}>
              <SelectTrigger className="h-9 w-28"><SelectValue placeholder="All" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All</SelectItem>
                <SelectItem value="long">Long</SelectItem>
                <SelectItem value="short">Short</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs">Strategy</Label>
            <Select value={filters.strategy_id || "all"} onValueChange={(v) => setFilters({ ...filters, strategy_id: v === "all" ? "" : v })}>
              <SelectTrigger className="h-9 w-40"><SelectValue placeholder="All" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All</SelectItem>
                {strategies.map((s) => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs">From</Label>
            <Input type="date" className="h-9" value={filters.start} onChange={(e) => setFilters({ ...filters, start: e.target.value })} />
          </div>
          <div>
            <Label className="text-xs">To</Label>
            <Input type="date" className="h-9" value={filters.end} onChange={(e) => setFilters({ ...filters, end: e.target.value })} />
          </div>
          <Button variant="outline" size="sm" onClick={() => setFilters({ symbol: "", side: "", strategy_id: "", tag: "", start: "", end: "" })}>Clear</Button>
        </div>

        <div className="bg-card border border-border rounded-md overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs uppercase tracking-wider text-muted-foreground border-b border-border bg-card sticky top-0">
                <th className="text-left py-2.5 px-4">Symbol</th>
                <th className="text-left py-2.5">Side</th>
                <th className="text-left py-2.5">Type</th>
                <th className="text-right py-2.5">Entry</th>
                <th className="text-right py-2.5">Exit</th>
                <th className="text-right py-2.5">Qty</th>
                <th className="text-right py-2.5">P&L</th>
                <th className="text-right py-2.5">R</th>
                <th className="text-left py-2.5 pl-4">Strategy</th>
                <th className="text-left py-2.5">Tags</th>
                <th className="text-right py-2.5 px-4">Date</th>
                <th className="py-2.5"></th>
              </tr>
            </thead>
            <tbody>
              {trades.map((t) => (
                <tr key={t.id} className="border-b border-border/40 hover:bg-accent/40 cursor-pointer" onClick={() => setDetail(t)} data-testid="trade-row">
                  <td className="py-2 px-4 font-mono font-semibold">{t.symbol}</td>
                  <td><span className={`text-xs font-semibold uppercase ${t.side === "long" ? "text-[#10B981]" : "text-[#EF4444]"}`}>{t.side}</span></td>
                  <td className="text-xs text-muted-foreground uppercase">{t.asset_type}</td>
                  <td className="text-right font-mono">{fmtNum(t.entry_price)}</td>
                  <td className="text-right font-mono">{t.exit_price ? fmtNum(t.exit_price) : <Badge className="bg-[#3B82F6]/15 text-[#3B82F6]">OPEN</Badge>}</td>
                  <td className="text-right font-mono">{t.quantity}</td>
                  <td className={`text-right font-mono font-bold ${plClass(t.pnl)}`}>{fmtMoney(t.pnl)}</td>
                  <td className={`text-right font-mono ${plClass(t.r_multiple)}`}>{t.r_multiple ? `${t.r_multiple}R` : "—"}</td>
                  <td className="pl-4 text-muted-foreground text-xs">{stratName(t.strategy_id)}</td>
                  <td>
                    <div className="flex gap-1 flex-wrap">
                      {t.tags?.slice(0, 2).map((tag) => (
                        <span key={tag} className="text-[10px] uppercase font-bold px-1.5 py-0.5 rounded" style={{ background: `${tagColor(tag)}22`, color: tagColor(tag) }}>{tag}</span>
                      ))}
                    </div>
                  </td>
                  <td className="text-right px-4 font-mono text-xs text-muted-foreground">{(t.exit_time || t.entry_time || "").slice(0, 10)}</td>
                  <td className="px-2"><button onClick={(e) => { e.stopPropagation(); del(t.id); }} className="text-muted-foreground hover:text-[#EF4444]"><Trash2 className="w-3.5 h-3.5" /></button></td>
                </tr>
              ))}
              {trades.length === 0 && <tr><td colSpan={12} className="py-12 text-center text-muted-foreground">No trades match filters.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      {/* Add / Edit dialog */}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-xl max-h-[90vh] overflow-y-auto" data-testid="trade-dialog">
          <DialogHeader><DialogTitle>{editing ? "Edit Trade" : "Add Trade"}</DialogTitle></DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Symbol"><Input value={form.symbol} onChange={(e) => setForm({ ...form, symbol: e.target.value })} data-testid="trade-symbol-input" /></Field>
            <Field label="Side">
              <Select value={form.side} onValueChange={(v) => setForm({ ...form, side: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="long">Long</SelectItem><SelectItem value="short">Short</SelectItem></SelectContent>
              </Select>
            </Field>
            <Field label="Asset">
              <Select value={form.asset_type} onValueChange={(v) => setForm({ ...form, asset_type: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="stock">Stock</SelectItem><SelectItem value="option">Option</SelectItem></SelectContent>
              </Select>
            </Field>
            <Field label="Status">
              <Select value={form.status} onValueChange={(v) => setForm({ ...form, status: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="closed">Closed</SelectItem><SelectItem value="open">Open</SelectItem></SelectContent>
              </Select>
            </Field>
            <Field label="Entry Price"><Input type="number" value={form.entry_price} onChange={(e) => setForm({ ...form, entry_price: e.target.value })} data-testid="trade-entry-input" /></Field>
            <Field label="Exit Price"><Input type="number" value={form.exit_price} onChange={(e) => setForm({ ...form, exit_price: e.target.value })} /></Field>
            <Field label="Quantity"><Input type="number" value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} /></Field>
            <Field label="Fees"><Input type="number" value={form.fees} onChange={(e) => setForm({ ...form, fees: e.target.value })} /></Field>
            <Field label="Risk ($)"><Input type="number" value={form.risk_amount} onChange={(e) => setForm({ ...form, risk_amount: e.target.value })} /></Field>
            <Field label="Strategy">
              <Select value={form.strategy_id || "none"} onValueChange={(v) => setForm({ ...form, strategy_id: v === "none" ? "" : v })}>
                <SelectTrigger><SelectValue placeholder="None" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">None</SelectItem>
                  {strategies.map((s) => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </Field>
            <Field label="MFE"><Input type="number" value={form.mfe} onChange={(e) => setForm({ ...form, mfe: e.target.value })} /></Field>
            <Field label="MAE"><Input type="number" value={form.mae} onChange={(e) => setForm({ ...form, mae: e.target.value })} /></Field>
            {form.asset_type === "option" && (
              <>
                <Field label="Expiry"><Input type="date" value={form.option_expiry || ""} onChange={(e) => setForm({ ...form, option_expiry: e.target.value })} /></Field>
                <Field label="Strike"><Input type="number" value={form.option_strike} onChange={(e) => setForm({ ...form, option_strike: e.target.value })} /></Field>
                <Field label="Right">
                  <Select value={form.option_right} onValueChange={(v) => setForm({ ...form, option_right: v })}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent><SelectItem value="call">Call</SelectItem><SelectItem value="put">Put</SelectItem></SelectContent>
                  </Select>
                </Field>
              </>
            )}
          </div>
          <div>
            <Label className="text-xs">Tags</Label>
            <div className="flex gap-1.5 flex-wrap mt-2">
              {tags.map((t) => (
                <button key={t.id} type="button" onClick={() => toggleTag(t.name)}
                  className="text-xs uppercase font-bold px-2 py-1 rounded border transition-all"
                  style={form.tags.includes(t.name)
                    ? { background: t.color, color: "#fff", borderColor: t.color }
                    : { borderColor: "var(--border)", color: t.color }}>
                  {t.name}
                </button>
              ))}
            </div>
          </div>
          <div>
            <Label className="text-xs">Notes</Label>
            <Textarea value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} rows={3} placeholder="Strategy reasoning, emotions, mistakes…" />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={save} className="bg-[#007AFF] hover:bg-[#3395FF] text-white" data-testid="save-trade-btn">{editing ? "Update" : "Add"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Detail dialog */}
      <Dialog open={!!detail} onOpenChange={(o) => !o && setDetail(null)}>
        <DialogContent className="max-w-lg" data-testid="trade-detail-dialog">
          {detail && (
            <>
              <DialogHeader>
                <DialogTitle className="font-mono">{detail.symbol} · <span className={detail.side === "long" ? "text-[#10B981]" : "text-[#EF4444]"}>{detail.side.toUpperCase()}</span></DialogTitle>
              </DialogHeader>
              <div className="grid grid-cols-3 gap-3 text-sm">
                <Field label="Entry"><span className="font-mono">{fmtNum(detail.entry_price)}</span></Field>
                <Field label="Exit"><span className="font-mono">{detail.exit_price ? fmtNum(detail.exit_price) : "—"}</span></Field>
                <Field label="P&L"><span className={`font-mono font-bold ${plClass(detail.pnl)}`}>{fmtMoney(detail.pnl)}</span></Field>
                <Field label="Qty"><span className="font-mono">{detail.quantity}</span></Field>
                <Field label="R-Multiple"><span className="font-mono">{detail.r_multiple ? `${detail.r_multiple}R` : "—"}</span></Field>
                <Field label="Source"><span className="capitalize">{detail.source}</span></Field>
                <Field label="MFE"><span className="font-mono text-[#10B981]">{detail.mfe ? fmtMoney(detail.mfe) : "—"}</span></Field>
                <Field label="MAE"><span className="font-mono text-[#EF4444]">{detail.mae ? fmtMoney(detail.mae) : "—"}</span></Field>
                <Field label="Account"><span className="uppercase">{detail.account}</span></Field>
              </div>
              <div className="flex gap-1.5 flex-wrap">
                {detail.tags?.map((tag) => (
                  <span key={tag} className="text-[10px] uppercase font-bold px-1.5 py-0.5 rounded" style={{ background: `${tagColor(tag)}22`, color: tagColor(tag) }}>{tag}</span>
                ))}
              </div>
              {detail.notes && <div className="bg-background border border-border rounded p-3 text-sm">{detail.notes}</div>}
              {detail.screenshot_url && <img src={detail.screenshot_url} alt="chart" className="rounded border border-border max-h-60 object-contain w-full" />}
              <div className="flex gap-2">
                <label className="flex-1">
                  <input type="file" accept="image/*" className="hidden" onChange={uploadShot} data-testid="upload-screenshot" />
                  <span className="flex items-center justify-center gap-2 h-9 rounded-md border border-border text-sm cursor-pointer hover:bg-accent"><Upload className="w-4 h-4" /> Attach Screenshot</span>
                </label>
                <Button variant="outline" onClick={() => openEdit(detail)} data-testid="edit-trade-btn">Edit</Button>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <div>
      <Label className="text-xs uppercase tracking-wider text-muted-foreground">{label}</Label>
      <div className="mt-1">{children}</div>
    </div>
  );
}
