import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Activity } from "lucide-react";
import { toast } from "sonner";

export default function Login() {
  const { login, register } = useAuth();
  const nav = useNavigate();
  const [mode, setMode] = useState("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("trader@tradehub.io");
  const [password, setPassword] = useState("trade1234");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      if (mode === "login") {
        await login(email, password);
        toast.success("Welcome back");
      } else {
        await register(name || "Trader", email, password);
        toast.success("Account created");
      }
      nav("/");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Something went wrong");
    } finally {
      setLoading(false);
    }
  };

  const switchMode = (m) => {
    setMode(m);
    if (m === "register") { setEmail(""); setPassword(""); }
    else { setEmail("trader@tradehub.io"); setPassword("trade1234"); }
  };

  return (
    <div className="dark min-h-screen bg-[#0A0A0A] text-white flex">
      <div className="hidden lg:flex flex-1 relative overflow-hidden">
        <img
          src="https://images.pexels.com/photos/12627677/pexels-photo-12627677.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940"
          alt="" className="absolute inset-0 w-full h-full object-cover opacity-60" />
        <div className="absolute inset-0 bg-gradient-to-t from-[#0A0A0A] via-[#0A0A0A]/40 to-transparent" />
        <div className="relative z-10 flex flex-col justify-end p-12">
          <h2 className="font-heading font-black text-5xl tracking-tight leading-none mb-3">
            Trade smarter.<br />Approve faster.
          </h2>
          <p className="text-white/60 max-w-md">
            Strategy-aware webhooks, multi-channel approvals, automated journaling and Tradervue-grade analytics — all in one command center.
          </p>
        </div>
      </div>
      <div className="w-full lg:w-[480px] flex items-center justify-center p-8">
        <form onSubmit={submit} className="w-full max-w-sm space-y-6" data-testid="login-form">
          <div className="flex items-center gap-2 mb-8">
            <div className="w-9 h-9 rounded bg-[#007AFF] flex items-center justify-center">
              <Activity className="w-5 h-5 text-white" strokeWidth={2.5} />
            </div>
            <span className="font-heading font-black text-3xl tracking-tight">TradeHub</span>
          </div>
          <div>
            <h1 className="font-heading font-bold text-2xl">{mode === "login" ? "Sign in" : "Create account"}</h1>
            <p className="text-sm text-white/50 mt-1">
              {mode === "login" ? "Access your trading command center." : "Start your own isolated trading workspace."}
            </p>
          </div>
          {mode === "register" && (
            <div className="space-y-2">
              <Label className="text-xs uppercase tracking-wider text-white/50">Name</Label>
              <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Your name"
                className="bg-[#141414] border-white/10 text-white" data-testid="register-name" />
            </div>
          )}
          <div className="space-y-2">
            <Label className="text-xs uppercase tracking-wider text-white/50">Email</Label>
            <Input value={email} onChange={(e) => setEmail(e.target.value)}
              className="bg-[#141414] border-white/10 text-white" data-testid="login-email" />
          </div>
          <div className="space-y-2">
            <Label className="text-xs uppercase tracking-wider text-white/50">Password</Label>
            <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
              className="bg-[#141414] border-white/10 text-white" data-testid="login-password" />
          </div>
          <Button type="submit" disabled={loading}
            className="w-full bg-[#007AFF] hover:bg-[#3395FF] text-white font-semibold" data-testid="login-submit">
            {loading ? "Please wait…" : mode === "login" ? "Sign In" : "Create Account"}
          </Button>
          <div className="text-center text-sm text-white/50">
            {mode === "login" ? (
              <>New here?{" "}
                <button type="button" onClick={() => switchMode("register")} className="text-[#3395FF] hover:underline" data-testid="switch-to-register">
                  Create an account
                </button>
              </>
            ) : (
              <>Already have an account?{" "}
                <button type="button" onClick={() => switchMode("login")} className="text-[#3395FF] hover:underline" data-testid="switch-to-login">
                  Sign in
                </button>
              </>
            )}
          </div>
        </form>
      </div>
    </div>
  );
}
