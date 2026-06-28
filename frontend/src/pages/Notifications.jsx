import React, { useEffect, useState, useCallback } from "react";
import api from "@/lib/api";
import { PageHeader } from "@/components/Shared";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Send, MessageCircle, Hash, Phone, Server } from "lucide-react";
import { toast } from "sonner";

export default function Notifications() {
  const [log, setLog] = useState([]);
  const [s, setS] = useState({ telegram: {}, discord: {}, whatsapp: {}, ibkr: {} });

  const load = useCallback(async () => {
    const [l, set] = await Promise.all([api.get("/notifications"), api.get("/settings")]);
    setLog(l.data);
    setS({ telegram: {}, discord: {}, whatsapp: {}, ibkr: {}, ...set.data });
  }, []);
  useEffect(() => { load(); }, [load]);

  const save = async () => {
    await api.put("/settings", s);
    toast.success("Settings saved");
  };

  const up = (group, key, val) => setS((prev) => ({ ...prev, [group]: { ...prev[group], [key]: val } }));

  return (
    <div className="fade-in">
      <PageHeader title="Notifications" subtitle="Delivery log & integration credentials" />
      <div className="p-8">
        <Tabs defaultValue="log">
          <TabsList className="bg-card border border-border">
            <TabsTrigger value="log" data-testid="tab-notif-log">Notification Log</TabsTrigger>
            <TabsTrigger value="settings" data-testid="tab-notif-settings">Settings</TabsTrigger>
          </TabsList>

          <TabsContent value="log">
            <div className="bg-card border border-border rounded-md p-5">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs uppercase tracking-wider text-muted-foreground border-b border-border">
                    <th className="text-left py-2">Platform</th>
                    <th className="text-left py-2">Message</th>
                    <th className="text-left py-2">Status</th>
                    <th className="text-left py-2">Response</th>
                    <th className="text-right py-2">Sent</th>
                  </tr>
                </thead>
                <tbody>
                  {log.map((n) => (
                    <tr key={n.id} className="border-b border-border/40">
                      <td className="py-2 capitalize font-semibold">{n.platform}</td>
                      <td className="text-muted-foreground max-w-xs truncate">{n.message}</td>
                      <td><Badge className={n.status === "delivered" ? "bg-[#10B981]/15 text-[#10B981]" : "bg-[#EF4444]/15 text-[#EF4444]"}>{n.status}</Badge></td>
                      <td className="text-muted-foreground capitalize">{n.response || "—"}</td>
                      <td className="text-right font-mono text-xs text-muted-foreground">{new Date(n.sent_at).toLocaleString()}</td>
                    </tr>
                  ))}
                  {log.length === 0 && <tr><td colSpan={5} className="py-10 text-center text-muted-foreground">No notifications sent yet. Approval-mode strategies trigger notifications.</td></tr>}
                </tbody>
              </table>
            </div>
          </TabsContent>

          <TabsContent value="settings">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <Card icon={MessageCircle} title="Telegram" color="#229ED9">
                <FieldI label="Bot Token" val={s.telegram.bot_token} onChange={(v) => up("telegram", "bot_token", v)} secret testId="tg-token" />
                <FieldI label="Chat ID" val={s.telegram.chat_id} onChange={(v) => up("telegram", "chat_id", v)} />
                <p className="text-xs text-muted-foreground">Set Telegram webhook to <code className="text-foreground">/api/webhook/telegram/callback</code> for inline approve/reject.</p>
              </Card>
              <Card icon={Hash} title="Discord" color="#5865F2">
                <FieldI label="Webhook URL" val={s.discord.webhook_url} onChange={(v) => up("discord", "webhook_url", v)} testId="dc-webhook" />
              </Card>
              <Card icon={Phone} title="WhatsApp (Twilio)" color="#25D366">
                <FieldI label="Account SID" val={s.whatsapp.account_sid} onChange={(v) => up("whatsapp", "account_sid", v)} />
                <FieldI label="Auth Token" val={s.whatsapp.auth_token} onChange={(v) => up("whatsapp", "auth_token", v)} secret />
                <FieldI label="From (whatsapp:+1...)" val={s.whatsapp.from_number} onChange={(v) => up("whatsapp", "from_number", v)} />
                <FieldI label="To (whatsapp:+1...)" val={s.whatsapp.to_number} onChange={(v) => up("whatsapp", "to_number", v)} />
                <p className="text-xs text-muted-foreground">Inbound reply webhook: <code className="text-foreground">/api/webhook/whatsapp/reply</code></p>
              </Card>
              <Card icon={Server} title="IBKR Gateway" color="#D81222">
                <div className="flex items-center justify-between">
                  <Label className="text-xs">Enable Live Trading</Label>
                  <Switch checked={!!s.ibkr.enabled} onCheckedChange={(v) => up("ibkr", "enabled", v)} data-testid="ibkr-enable" />
                </div>
                <FieldI label="Host" val={s.ibkr.host || "127.0.0.1"} onChange={(v) => up("ibkr", "host", v)} />
                <FieldI label="Port" val={s.ibkr.port || "7497"} onChange={(v) => up("ibkr", "port", v)} />
                <p className="text-xs text-muted-foreground">Requires TWS/IB Gateway reachable from the backend host. Otherwise paper simulation is used.</p>
              </Card>
            </div>
            <Button onClick={save} className="mt-4 bg-[#007AFF] hover:bg-[#3395FF] text-white" data-testid="save-settings-btn">
              <Send className="w-4 h-4 mr-2" /> Save Settings
            </Button>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}

function Card({ icon: Icon, title, color, children }) {
  return (
    <div className="bg-card border border-border rounded-md p-5 space-y-3">
      <div className="flex items-center gap-2">
        <div className="w-8 h-8 rounded flex items-center justify-center" style={{ background: `${color}22` }}>
          <Icon className="w-4 h-4" style={{ color }} />
        </div>
        <h3 className="font-heading font-bold text-lg">{title}</h3>
      </div>
      {children}
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
