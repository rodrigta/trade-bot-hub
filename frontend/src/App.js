import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { ThemeProvider } from "@/context/ThemeContext";
import Layout from "@/components/Layout";
import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import Strategies from "@/pages/Strategies";
import StrategyDetail from "@/pages/StrategyDetail";
import Bot from "@/pages/Bot";
import Journal from "@/pages/Journal";
import Analysis from "@/pages/Analysis";
import Notifications from "@/pages/Notifications";

function Protected({ children }) {
  const { user, ready } = useAuth();
  if (!ready) return <div className="h-screen flex items-center justify-center bg-background text-muted-foreground">Loading…</div>;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route element={<Protected><Layout /></Protected>}>
              <Route path="/" element={<Dashboard />} />
              <Route path="/strategies" element={<Strategies />} />
              <Route path="/strategies/:id" element={<StrategyDetail />} />
              <Route path="/bot" element={<Bot />} />
              <Route path="/journal" element={<Journal />} />
              <Route path="/analysis" element={<Analysis />} />
              <Route path="/notifications" element={<Notifications />} />
            </Route>
          </Routes>
        </BrowserRouter>
        <Toaster position="top-right" richColors theme="dark" />
      </AuthProvider>
    </ThemeProvider>
  );
}

export default App;
