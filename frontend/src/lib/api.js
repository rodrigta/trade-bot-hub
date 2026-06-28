import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

const api = axios.create({ baseURL: API });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("th_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401 && !window.location.pathname.includes("login")) {
      localStorage.removeItem("th_token");
      window.location.href = "/login";
    }
    return Promise.reject(err);
  }
);

export default api;

export function fmtMoney(n) {
  if (n === null || n === undefined) return "—";
  const sign = n < 0 ? "-" : "";
  return `${sign}$${Math.abs(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function fmtNum(n, d = 2) {
  if (n === null || n === undefined) return "—";
  return Number(n).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });
}

export function plClass(n) {
  if (n === null || n === undefined || n === 0) return "text-muted-foreground";
  return n > 0 ? "text-[#10B981]" : "text-[#EF4444]";
}
