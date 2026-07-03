import React, { useEffect, useState, useCallback } from "react";
import api from "@/lib/api";
import { PageHeader } from "@/components/Shared";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { UserPlus, Trash2, Shield, User } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";

export default function Users() {
  const { user } = useAuth();
  const [users, setUsers] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", email: "", password: "" });

  const load = useCallback(async () => {
    const { data } = await api.get("/users");
    setUsers(data);
  }, []);
  useEffect(() => { load(); }, [load]);

  const create = async () => {
    if (!form.email.trim() || !form.password.trim()) return toast.error("Email and password required");
    try {
      await api.post("/users", form);
      toast.success("User created");
      setOpen(false);
      setForm({ name: "", email: "", password: "" });
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed");
    }
  };

  const del = async (u) => {
    if (!window.confirm(`Delete ${u.email} and ALL their data? This cannot be undone.`)) return;
    try {
      await api.delete(`/users/${u.id}`);
      toast.success("User deleted");
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed");
    }
  };

  return (
    <div className="fade-in">
      <PageHeader title="Users" subtitle="Manage accounts — each user has a fully isolated workspace">
        <Button onClick={() => setOpen(true)} className="bg-[#007AFF] hover:bg-[#3395FF] text-white" data-testid="new-user-btn">
          <UserPlus className="w-4 h-4 mr-2" /> Add User
        </Button>
      </PageHeader>

      <div className="p-8">
        <div className="bg-card border border-border rounded-md overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs uppercase tracking-wider text-muted-foreground border-b border-border">
                <th className="text-left py-3 px-4">User</th>
                <th className="text-left py-3">Email</th>
                <th className="text-left py-3">Role</th>
                <th className="text-right py-3">Strategies</th>
                <th className="text-right py-3">Trades</th>
                <th className="text-right py-3 px-4">Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-b border-border/40 hover:bg-accent/40" data-testid="user-row">
                  <td className="py-3 px-4 font-semibold flex items-center gap-2">
                    {u.is_admin ? <Shield className="w-4 h-4 text-[#007AFF]" /> : <User className="w-4 h-4 text-muted-foreground" />}
                    {u.name || "—"}
                  </td>
                  <td className="text-muted-foreground">{u.email}</td>
                  <td>
                    <Badge className={u.is_admin ? "bg-[#007AFF]/15 text-[#007AFF]" : "bg-muted text-muted-foreground"}>
                      {u.is_admin ? "ADMIN" : "USER"}
                    </Badge>
                  </td>
                  <td className="text-right font-mono">{u.strategy_count}</td>
                  <td className="text-right font-mono">{u.trade_count}</td>
                  <td className="text-right px-4">
                    {u.id === user?.id ? (
                      <span className="text-xs text-muted-foreground">You</span>
                    ) : (
                      <button onClick={() => del(u)} className="text-muted-foreground hover:text-[#EF4444]" data-testid={`delete-user-${u.id}`}>
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-md" data-testid="user-dialog">
          <DialogHeader><DialogTitle>Add User</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div>
              <Label className="text-xs">Name</Label>
              <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="user-name-input" />
            </div>
            <div>
              <Label className="text-xs">Email</Label>
              <Input value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} data-testid="user-email-input" />
            </div>
            <div>
              <Label className="text-xs">Password</Label>
              <Input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} data-testid="user-password-input" />
            </div>
            <p className="text-xs text-muted-foreground">The new user starts with an empty, isolated workspace and default tags.</p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={create} className="bg-[#007AFF] hover:bg-[#3395FF] text-white" data-testid="save-user-btn">Create</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
