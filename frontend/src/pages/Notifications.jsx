import React, { useEffect, useState, useCallback } from "react";
import api from "@/lib/api";
import { PageHeader } from "@/components/Shared";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Send, MessageCircle, Hash, Phone, Bell, User, Users, FlaskConical } from "lucide-react";
import { toast } from "sonner";

const EVENTS = [
  { id: "signal", label: "Signals" },
  { id: "order_success", label: "Order Filled" },
  { id: "order_failure", label: "Order Failed" },
];
const ALL_EVENTS = EVENTS.map((e) => e.id);

const emptyTarget = { enabled: false, bot_token: "", chat_id: "" };

export default function Notifications() {
  const [log, setLog] = useState([]);
  const [s, setS] = useState(null);
  const [testing, setTesting] = useState("");

  const load = useCallback(async () => {
    const [l, set] = await Promise.all([api.get("/notifications"), api.get("/settings")]);
    setLog(l.data);
    const d = set.data || {};
    setS({
      telegram: {
        events: d.telegram?.events || ALL_EVENTS,
        personal: { ...emptyTarget, ...(d.telegram?.personal || {}) },
        group: { ...emptyTarget, ...(d.telegram?.group || {}) },
      },
      discord: { events: d.discord?.events || ALL_EVENTS, chat_type: d.discord?.chat_type || "group", webhook_url: d.discord?.webhook_url || "" },
      whatsapp: {
        events: d.whatsapp?.events || ALL_EVENTS,
        account_sid: d.whatsapp?.account_sid || "", auth_token: d.whatsapp?.auth_token || "",
        from_number: d.whatsapp?.from_number || "", to_number: d.whatsapp?.to_number || "",
      },
      ibkr: d.ibkr || {},
      auto_trade_enabled: !!d.auto_trade_enabled,
    });
  }, []);
  useEffect(() => { load(); }, [load]);

  const save = async () => {
    await api.put("/settings", s);
    toast.success("Settings saved");
    load();
  };

  const test = async (platform) => {
    // Persist first so the backend tests against the latest credentials.
    await api.put("/settings", s);
    setTesting(platform);
    try {
      const { data } = await api.post("/notifications/test", { platform });
      if (data.ok) toast.success(`${platform} test delivered — check your chat!`);
      else toast.error(`${platform} test failed: ${JSON.stringify(data.detail)?.slice(0, 160)}`);
      load();
    } finally {
      setTesting("");
    }
  };

  const toggleEvent = (platform, ev) => {
    setS((p) => {
      const cur = p[platform].events || [];
      const events = cur.includes(ev) ? cur.filter((x) => x !== ev) : [...cur, ev];
      return { ...p, [platform]: { ...p[platform], events } };
    });
  };

  const setTg = (kind, key, val) =>
    setS((p) => ({ ...p, telegram: { ...p.telegram, [kind]: { ...p.telegram[kind], [key]: val } } }));
  const setPlat = (platform, key, val) =>
    setS((p) => ({ ...p, [platform]: { ...p[platform], [key]: val } }));

  if (!s) return <div className="p-8 text-muted-foreground">Loading…</div>;

  return (
    <div className="fade-in">
      <PageHeader title="Notifications" subtitle="Delivery log & integration credentials" />
      <div className="p-8">
        <Tabs defaultValue="settings">
          <TabsList className="bg-card border border-border">
            <TabsTrigger value="settings" data-testid="tab-notif-settings">Settings</TabsTrigger>
            <TabsTrigger value="log" data-testid="tab-notif-log">Notification Log</TabsTrigger>
          </TabsList>

          <TabsContent value="settings">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {/* Telegram */}
              <Card icon={MessageCircle} title="Telegram" color="#229ED9"
                events={s.telegram.events} onEvent={(e) => toggleEvent("telegram", e)}
                onTest={() => test("telegram")} testing={testing === "telegram"} testId="telegram">
                <TgTarget kind="personal" icon={User} label="Personal chat" t={s.telegram.personal} set={setTg}
                  hint="Personal chat_id is a positive number (get it from @userinfobot)." />
                <TgTarget kind="group" icon={Users} label="Group chat" t={s.telegram.group} set={setTg}
                  hint="Group chat_id is negative (e.g. -100…). Use a dedicated bot added to the group." />
                <p className="text-xs text-muted-foreground">Approve/Reject inline buttons post back to <code className="text-foreground">/api/webhook/telegram/callback</code> (set this as your bot webhook).</p>
              </Card>

              {/* Discord */}
              <Card icon={Hash} title="Discord" color="#5865F2"
                events={s.discord.events} onEvent={(e) => toggleEvent("discord", e)}
                onTest={() => test("discord")} testing={testing === "discord"} testId="discord">
                <div>
                  <Label className="text-xs">Chat Type</Label>
                  <Select value={s.discord.chat_type} onValueChange={(v) => setPlat("discord", "chat_type", v)}>
                    <SelectTrigger data-testid="discord-chattype"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="group">Group / Server channel</SelectItem>
                      <SelectItem value="personal">Personal / DM channel</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <FieldI label="Webhook URL" val={s.discord.webhook_url} onChange={(v) => setPlat("discord", "webhook_url", v)} testId="dc-webhook" />
                <p className="text-xs text-muted-foreground">A Discord webhook already points to one channel — create a separate webhook per channel/group.</p>
              </Card>

              {/* WhatsApp */}
              <Card icon={Phone} title="WhatsApp (Twilio)" color="#25D366"
                events={s.whatsapp.events} onEvent={(e) => toggleEvent("whatsapp", e)}
                onTest={() => test("whatsapp")} testing={testing === "whatsapp"} testId="whatsapp">
                <FieldI label="Account SID" val={s.whatsapp.account_sid} onChange={(v) => setPlat("whatsapp", "account_sid", v)} />
                <FieldI label="Auth Token" val={s.whatsapp.auth_token} onChange={(v) => setPlat("whatsapp", "auth_token", v)} secret />
                <FieldI label="From (whatsapp:+1...)" val={s.whatsapp.from_number} onChange={(v) => setPlat("whatsapp", "from_number", v)} />
                <FieldI label="To (whatsapp:+1...)" val={s.whatsapp.to_number} onChange={(v) => setPlat("whatsapp", "to_number", v)} />
                <p className="text-xs text-muted-foreground">Reply YES/NO webhook: <code className="text-foreground">/api/webhook/whatsapp/reply</code></p>
              </Card>

              <div className="bg-card border border-border rounded-md p-5 flex flex-col justify-center gap-2">
                <div className="flex items-center gap-2"><Bell className="w-4 h-4 text-[#007AFF]" /><h3 className="font-heading font-bold text-lg">Broker & Auto-Trade</h3></div>
                <p className="text-sm text-muted-foreground">Broker connection and the Auto-Trade master switch live on the <strong>Bot</strong> page.</p>
              </div>
            </div>
            <Button onClick={save} className="mt-4 bg-[#007AFF] hover:bg-[#3395FF] text-white" data-testid="save-settings-btn">
              <Send className="w-4 h-4 mr-2" /> Save Settings
            </Button>
          </TabsContent>

          <TabsContent value="log">
            <div className="bg-card border border-border rounded-md p-5">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs uppercase tracking-wider text-muted-foreground border-b border-border">
                    <th className="text-left py-2">Platform</th>
                    <th className="text-left py-2">Target</th>
                    <th className="text-left py-2">Event</th>
                    <th className="text-left py-2">Message</th>
                    <th className="text-left py-2">Status</th>
                    <th className="text-right py-2">Sent</th>
                  </tr>
                </thead>
                <tbody>
                  {log.map((n) => (
                    <tr key={n.id} className="border-b border-border/40">
                      <td className="py-2 capitalize font-semibold">{n.platform}</td>
                      <td className="text-muted-foreground capitalize">{n.target || "—"}</td>
                      <td><Badge variant="outline" className="text-xs">{(n.event || "signal").replace("_", " ")}</Badge></td>
                      <td className="text-muted-foreground max-w-xs truncate">{n.message}</td>
                      <td><Badge className={n.status === "delivered" ? "bg-[#10B981]/15 text-[#10B981]" : "bg-[#EF4444]/15 text-[#EF4444]"}>{n.status}</Badge></td>
                      <td className="text-right font-mono text-xs text-muted-foreground">{new Date(n.sent_at).toLocaleString()}</td>
                    </tr>
                  ))}
                  {log.length === 0 && <tr><td colSpan={6} className="py-10 text-center text-muted-foreground">No notifications yet. Send a test above or fire a webhook.</td></tr>}
                </tbody>
              </table>
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}

function Card({ icon: Icon, title, color, events, onEvent, onTest, testing, testId, children }) {
  return (
    <div className="bg-card border border-border rounded-md p-5 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded flex items-center justify-center" style={{ background: `${color}22` }}>
            <Icon className="w-4 h-4" style={{ color }} />
          </div>
          <h3 className="font-heading font-bold text-lg">{title}</h3>
        </div>
        <Button variant="outline" size="sm" onClick={onTest} disabled={testing} data-testid={`test-${testId}`}>
          <FlaskConical className="w-4 h-4 mr-1" /> {testing ? "Sending…" : "Send Test"}
        </Button>
      </div>
      {children}
      <div>
        <Label className="text-xs">Send which notifications?</Label>
        <div className="flex gap-2 mt-2">
          {EVENTS.map((e) => (
            <button key={e.id} type="button" onClick={() => onEvent(e.id)}
              data-testid={`${testId}-event-${e.id}`}
              className={`px-3 py-1.5 rounded-md text-xs font-semibold border transition-all ${
                events?.includes(e.id)
                  ? "bg-[#007AFF] text-white border-[#007AFF]"
                  : "border-border text-muted-foreground hover:border-white/30"
              }`}>
              {e.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function TgTarget({ kind, icon: Icon, label, t, set, hint }) {
  return (
    <div className="border border-border rounded-md p-3 space-y-2 bg-background">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm font-semibold"><Icon className="w-4 h-4 text-muted-foreground" /> {label}</div>
        <Switch checked={!!t.enabled} onCheckedChange={(v) => set(kind, "enabled", v)} data-testid={`tg-${kind}-enable`} />
      </div>
      {t.enabled && (
        <>
          <FieldI label="Bot Token" val={t.bot_token} onChange={(v) => set(kind, "bot_token", v)} secret testId={`tg-${kind}-token`} />
          <FieldI label="Chat ID" val={t.chat_id} onChange={(v) => set(kind, "chat_id", v)} testId={`tg-${kind}-chatid`} />
          <p className="text-[11px] text-muted-foreground">{hint}</p>
        </>
      )}
    </div>
  );
}

function FieldI({ label, val, onChange, secret, testId }) {
  return (
    <div>
      <Label className="text-xs">{label}</Label>
      <Input type={secret ? "password" : "text"} value={val || ""} onChange={(e) => onChange(e.target.value)} data-testid={testId} />
    </div>
  );
}
