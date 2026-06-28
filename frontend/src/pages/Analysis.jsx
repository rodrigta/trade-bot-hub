import React, { useEffect, useState, useCallback } from "react";
import api, { fmtMoney, fmtNum, plClass } from "@/lib/api";
import { PageHeader, StatCard } from "@/components/Shared";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  ResponsiveContainer, AreaChart, Area, BarChart, Bar, ScatterChart, Scatter,
  XAxis, YAxis, ZAxis, Tooltip, CartesianGrid, Cell, ReferenceLine,
} from "recharts";
import { ChevronLeft, ChevronRight } from "lucide-react";

const GREEN = "#10B981", RED = "#EF4444", BLUE = "#007AFF";
const tip = { background: "#141414", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 6, fontSize: 12, color: "#fff" };

export default function Analysis() {
  const [ov, setOv] = useState(null);
  const [eq, setEq] = useState({ points: [], max_drawdown: 0 });
  const [bySymbol, setBySymbol] = useState([]);
  const [byStrategy, setByStrategy] = useState([]);
  const [byTag, setByTag] = useState([]);
  const [bySide, setBySide] = useState([]);
  const [tod, setTod] = useState([]);
  const [mfe, setMfe] = useState([]);
  const [comp, setComp] = useState([]);
  const [cal, setCal] = useState(null);
  const [calDate, setCalDate] = useState(new Date());

  const loadCal = useCallback(async (d) => {
    const { data } = await api.get("/analytics/calendar", { params: { year: d.getFullYear(), month: d.getMonth() + 1 } });
    setCal(data);
  }, []);

  useEffect(() => {
    Promise.all([
      api.get("/analytics/overview"),
      api.get("/analytics/equity-curve"),
      api.get("/analytics/by/symbol"),
      api.get("/analytics/by/strategy"),
      api.get("/analytics/by/tag"),
      api.get("/analytics/by/side"),
      api.get("/analytics/time-of-day"),
      api.get("/analytics/mfe-mae"),
      api.get("/analytics/strategy-comparison"),
    ]).then(([o, e, sy, st, tg, sd, td, mf, cp]) => {
      setOv(o.data); setEq(e.data); setBySymbol(sy.data); setByStrategy(st.data);
      setByTag(tg.data); setBySide(sd.data); setTod(td.data); setMfe(mf.data); setComp(cp.data);
    });
  }, []);
  useEffect(() => { loadCal(calDate); }, [calDate, loadCal]);

  return (
    <div className="fade-in">
      <PageHeader title="Analysis & Reports" subtitle="Tradervue-style performance breakdowns" />
      <div className="p-8 space-y-6">
        {ov && (
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
            <StatCard label="Net P&L" value={<span className={plClass(ov.total_pnl)}>{fmtMoney(ov.total_pnl)}</span>} />
            <StatCard label="Win Rate" value={`${ov.win_rate}%`} />
            <StatCard label="Profit Factor" value={fmtNum(ov.profit_factor)} />
            <StatCard label="Expectancy" value={`${ov.expectancy}R`} />
            <StatCard label="Max DD" value={<span className="text-[#EF4444]">{fmtMoney(eq.max_drawdown)}</span>} />
            <StatCard label="Best Trade" value={<span className="text-[#10B981]">{fmtMoney(ov.largest_win)}</span>} />
            <StatCard label="Worst Trade" value={<span className="text-[#EF4444]">{fmtMoney(ov.largest_loss)}</span>} />
          </div>
        )}

        <Tabs defaultValue="calendar">
          <TabsList className="bg-card border border-border flex-wrap h-auto">
            <TabsTrigger value="calendar" data-testid="tab-calendar">Calendar</TabsTrigger>
            <TabsTrigger value="equity" data-testid="tab-equity">Equity & Drawdown</TabsTrigger>
            <TabsTrigger value="breakdown" data-testid="tab-breakdown">Breakdowns</TabsTrigger>
            <TabsTrigger value="mfe" data-testid="tab-mfe">MFE / MAE</TabsTrigger>
            <TabsTrigger value="strategies" data-testid="tab-strategies">Strategy Compare</TabsTrigger>
          </TabsList>

          {/* CALENDAR */}
          <TabsContent value="calendar">
            <CalendarView cal={cal} date={calDate} setDate={setCalDate} />
          </TabsContent>

          {/* EQUITY */}
          <TabsContent value="equity">
            <div className="bg-card border border-border rounded-md p-5">
              <h3 className="font-heading font-bold text-lg mb-4">Cumulative Equity</h3>
              <ResponsiveContainer width="100%" height={300}>
                <AreaChart data={eq.points}>
                  <defs>
                    <linearGradient id="eq2" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={BLUE} stopOpacity={0.4} />
                      <stop offset="100%" stopColor={BLUE} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                  <XAxis dataKey="i" tick={{ fontSize: 11, fill: "#71717A" }} />
                  <YAxis tick={{ fontSize: 11, fill: "#71717A" }} tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} />
                  <Tooltip contentStyle={tip} formatter={(v) => fmtMoney(v)} />
                  <Area type="monotone" dataKey="cumulative" stroke={BLUE} strokeWidth={2} fill="url(#eq2)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
            <div className="bg-card border border-border rounded-md p-5 mt-4">
              <h3 className="font-heading font-bold text-lg mb-4">Drawdown</h3>
              <ResponsiveContainer width="100%" height={200}>
                <AreaChart data={eq.points}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                  <XAxis dataKey="i" tick={{ fontSize: 11, fill: "#71717A" }} />
                  <YAxis tick={{ fontSize: 11, fill: "#71717A" }} tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} />
                  <Tooltip contentStyle={tip} formatter={(v) => fmtMoney(v)} />
                  <Area type="monotone" dataKey="drawdown" stroke={RED} strokeWidth={1.5} fill={RED} fillOpacity={0.15} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </TabsContent>

          {/* BREAKDOWNS */}
          <TabsContent value="breakdown">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <BreakdownTable title="By Symbol" rows={bySymbol} />
              <BreakdownTable title="By Strategy" rows={byStrategy} />
              <BreakdownTable title="By Tag / Setup" rows={byTag} />
              <BreakdownTable title="Long vs Short" rows={bySide} />
              <div className="bg-card border border-border rounded-md p-5 lg:col-span-2">
                <h3 className="font-heading font-bold text-lg mb-4">P&L by Time of Day</h3>
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={tod}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                    <XAxis dataKey="hour" tick={{ fontSize: 11, fill: "#71717A" }} tickFormatter={(h) => `${h}:00`} />
                    <YAxis tick={{ fontSize: 11, fill: "#71717A" }} />
                    <Tooltip contentStyle={tip} formatter={(v) => fmtMoney(v)} />
                    <Bar dataKey="pnl" radius={[3, 3, 0, 0]}>
                      {tod.map((d, i) => <Cell key={i} fill={d.pnl >= 0 ? GREEN : RED} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </TabsContent>

          {/* MFE MAE */}
          <TabsContent value="mfe">
            <div className="bg-card border border-border rounded-md p-5">
              <h3 className="font-heading font-bold text-lg mb-1">MFE / MAE Scatter</h3>
              <p className="text-xs text-muted-foreground mb-4">Max favorable (x) vs max adverse excursion (y), colored by outcome.</p>
              <ResponsiveContainer width="100%" height={360}>
                <ScatterChart>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                  <XAxis type="number" dataKey="mfe" name="MFE" tick={{ fontSize: 11, fill: "#71717A" }} tickFormatter={(v) => `$${(v / 1000).toFixed(1)}k`} />
                  <YAxis type="number" dataKey="mae" name="MAE" tick={{ fontSize: 11, fill: "#71717A" }} tickFormatter={(v) => `$${(v / 1000).toFixed(1)}k`} />
                  <ZAxis range={[60, 60]} />
                  <ReferenceLine y={0} stroke="rgba(255,255,255,0.2)" />
                  <Tooltip contentStyle={tip} cursor={{ strokeDasharray: "3 3" }}
                    formatter={(v, n) => [fmtMoney(v), n]} labelFormatter={() => ""} />
                  <Scatter data={mfe}>
                    {mfe.map((d, i) => <Cell key={i} fill={d.pnl >= 0 ? GREEN : RED} />)}
                  </Scatter>
                </ScatterChart>
              </ResponsiveContainer>
            </div>
          </TabsContent>

          {/* STRATEGY COMPARE */}
          <TabsContent value="strategies">
            <div className="bg-card border border-border rounded-md p-5">
              <h3 className="font-heading font-bold text-lg mb-4">Strategy P&L Comparison</h3>
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={comp}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                  <XAxis dataKey="name" tick={{ fontSize: 11, fill: "#71717A" }} />
                  <YAxis tick={{ fontSize: 11, fill: "#71717A" }} tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} />
                  <Tooltip contentStyle={tip} formatter={(v) => fmtMoney(v)} />
                  <Bar dataKey="pnl" radius={[3, 3, 0, 0]}>
                    {comp.map((d, i) => <Cell key={i} fill={d.pnl >= 0 ? GREEN : RED} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
              <table className="w-full text-sm mt-4">
                <thead>
                  <tr className="text-xs uppercase tracking-wider text-muted-foreground border-b border-border">
                    <th className="text-left py-2">Strategy</th>
                    <th className="text-right py-2">Trades</th>
                    <th className="text-right py-2">Win Rate</th>
                    <th className="text-right py-2">Expectancy</th>
                    <th className="text-right py-2">P&L</th>
                  </tr>
                </thead>
                <tbody>
                  {comp.map((c) => (
                    <tr key={c.name} className="border-b border-border/40">
                      <td className="py-2 font-semibold">{c.name}</td>
                      <td className="text-right font-mono">{c.trades}</td>
                      <td className="text-right font-mono">{c.win_rate}%</td>
                      <td className="text-right font-mono">{c.expectancy}R</td>
                      <td className={`text-right font-mono font-bold ${plClass(c.pnl)}`}>{fmtMoney(c.pnl)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}

function BreakdownTable({ title, rows }) {
  return (
    <div className="bg-card border border-border rounded-md p-5">
      <h3 className="font-heading font-bold text-lg mb-3">{title}</h3>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-xs uppercase tracking-wider text-muted-foreground border-b border-border">
            <th className="text-left py-2">Key</th>
            <th className="text-right py-2">Trades</th>
            <th className="text-right py-2">Win%</th>
            <th className="text-right py-2">P&L</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key} className="border-b border-border/40">
              <td className="py-2 font-semibold capitalize">{r.key}</td>
              <td className="text-right font-mono">{r.trades}</td>
              <td className="text-right font-mono">{r.win_rate}%</td>
              <td className={`text-right font-mono font-bold ${plClass(r.pnl)}`}>{fmtMoney(r.pnl)}</td>
            </tr>
          ))}
          {rows.length === 0 && <tr><td colSpan={4} className="py-6 text-center text-muted-foreground">No data</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

function CalendarView({ cal, date, setDate }) {
  const year = date.getFullYear(), month = date.getMonth();
  const first = new Date(year, month, 1);
  const startDow = first.getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const cells = [];
  for (let i = 0; i < startDow; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(d);
  const days = cal?.days || {};
  const monthName = first.toLocaleString("default", { month: "long", year: "numeric" });

  return (
    <div className="bg-card border border-border rounded-md p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-heading font-bold text-xl">{monthName}</h3>
        <div className="flex items-center gap-3">
          <span className={`font-mono font-bold ${plClass(cal?.month_pnl)}`}>{fmtMoney(cal?.month_pnl)}</span>
          <span className="text-xs text-muted-foreground">{cal?.trading_days || 0} trading days</span>
          <Button variant="outline" size="sm" onClick={() => setDate(new Date(year, month - 1, 1))}><ChevronLeft className="w-4 h-4" /></Button>
          <Button variant="outline" size="sm" onClick={() => setDate(new Date(year, month + 1, 1))}><ChevronRight className="w-4 h-4" /></Button>
        </div>
      </div>
      <div className="grid grid-cols-7 gap-1.5">
        {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((d) => (
          <div key={d} className="text-center text-xs font-bold uppercase tracking-wider text-muted-foreground py-1">{d}</div>
        ))}
        {cells.map((d, i) => {
          if (d === null) return <div key={i} />;
          const key = `${year}-${String(month + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
          const info = days[key];
          const bg = info ? (info.pnl >= 0 ? "rgba(16,185,129,0.15)" : "rgba(239,68,68,0.15)") : "transparent";
          const bc = info ? (info.pnl >= 0 ? "rgba(16,185,129,0.4)" : "rgba(239,68,68,0.4)") : "var(--border)";
          return (
            <div key={i} className="aspect-square rounded border p-1.5 flex flex-col justify-between"
              style={{ background: bg, borderColor: bc }} data-testid={info ? `cal-day-${key}` : undefined}>
              <span className="text-xs text-muted-foreground">{d}</span>
              {info && (
                <div className="text-right">
                  <div className={`text-xs font-mono font-bold ${info.pnl >= 0 ? "text-[#10B981]" : "text-[#EF4444]"}`}>
                    {info.pnl >= 0 ? "+" : ""}{(info.pnl / 1000).toFixed(1)}k
                  </div>
                  <div className="text-[10px] text-muted-foreground">{info.trades}t</div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
