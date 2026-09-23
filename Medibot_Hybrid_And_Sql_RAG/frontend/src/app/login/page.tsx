"use client";

import { useState, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { login } from "@/lib/api";

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [sessionExpired, setSessionExpired] = useState(false);
  const searchParams = useSearchParams();

  // Check if redirected due to session expiry
  useEffect(() => {
    if (searchParams.get("expired") === "true") {
      setSessionExpired(true);
    }
  }, [searchParams]);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      // login() stores the signed token and user details in localStorage.
      await login({ username, password });
      window.location.href = "/chat";
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 via-blue-900 to-slate-900">
      <div className="bg-gradient-to-b from-slate-800/90 to-slate-900/90 backdrop-blur-xl p-8 rounded-xl shadow-lg w-full max-w-md border border-blue-400/30">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="flex items-center justify-center space-x-3 mb-3">
            <div className="w-12 h-12 bg-gradient-to-br from-blue-500 to-cyan-400 rounded-xl flex items-center justify-center shadow-lg shadow-blue-500/30">
              <svg className="w-8 h-8 text-white" fill="currentColor" viewBox="0 0 24 24">
                <path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-1 11h-4v4h-4v-4H6v-4h4V6h4v4h4v4z"/>
              </svg>
            </div>
            <h1 className="text-4xl font-bold bg-gradient-to-r from-blue-400 to-cyan-300 bg-clip-text text-transparent">MediBot</h1>
          </div>
          <p className="text-blue-300/70">MediAssist Health Network</p>
          <p className="text-sm text-blue-400/50 mt-1">Intelligent Medical Assistant</p>
        </div>

        {/* Session Expired Message */}
        {sessionExpired && (
          <div className="mb-6 text-amber-300 text-sm bg-amber-900/30 p-3 rounded-lg border border-amber-500/30 text-center">
            Your session has expired. Please log in again.
          </div>
        )}

        {/* Login Form */}
        <form onSubmit={handleLogin} className="space-y-5">
          <div>
            <label htmlFor="username" className="block text-sm font-semibold text-blue-300/70 mb-1">
              Username
            </label>
            <input
              type="text"
              id="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full px-4 py-3 border border-[#147CFA]/50 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#147CFA] focus:border-transparent text-white bg-[#147CFA]/30 placeholder-blue-200/60"
              placeholder="Enter username"
              required
            />
          </div>

          <div>
            <label htmlFor="password" className="block text-sm font-semibold text-blue-300/70 mb-1">
              Password
            </label>
            <input
              type="password"
              id="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-4 py-3 border border-[#147CFA]/50 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#147CFA] focus:border-transparent text-white bg-[#147CFA]/30 placeholder-blue-200/60"
              placeholder="Enter password"
              required
            />
          </div>

          {/* Error Message */}
          {error && (
            <div className="text-red-400 text-sm bg-red-900/30 p-3 rounded-lg border border-red-500/30">
              {error}
            </div>
          )}

          {/* Submit Button */}
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-gradient-to-r from-blue-600 to-cyan-500 text-white py-3 px-4 rounded-lg font-semibold hover:from-blue-500 hover:to-cyan-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-slate-900 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-lg shadow-blue-500/30"
          >
            {loading ? "Logging in..." : "Login"}
          </button>
        </form>

        {/* Demo Accounts */}
        <div className="mt-8 pt-6 border-t border-blue-400/30">
          <p className="text-sm font-semibold text-blue-300/70 text-center mb-4 uppercase tracking-wider">Demo Accounts</p>
          <div className="grid grid-cols-1 gap-2 text-sm">
            <div className="flex justify-between items-center bg-blue-800/30 p-3 rounded-lg border border-blue-400/20">
              <span className="font-bold text-blue-300">dr.mehta</span>
              <span className="text-blue-400/70">doctor</span>
              <span className="px-2 py-1 bg-blue-600/50 text-blue-200 rounded text-xs">doctor</span>
            </div>
            <div className="flex justify-between items-center bg-green-800/30 p-3 rounded-lg border border-green-400/20">
              <span className="font-bold text-green-300">nurse.priya</span>
              <span className="text-green-400/70">nurse</span>
              <span className="px-2 py-1 bg-green-600/50 text-green-200 rounded text-xs">nurse</span>
            </div>
            <div className="flex justify-between items-center bg-purple-800/30 p-3 rounded-lg border border-purple-400/20">
              <span className="font-bold text-purple-300">billing.ravi</span>
              <span className="text-purple-400/70">billing_executive</span>
              <span className="px-2 py-1 bg-purple-600/50 text-purple-200 rounded text-xs">billing</span>
            </div>
            <div className="flex justify-between items-center bg-orange-800/30 p-3 rounded-lg border border-orange-400/20">
              <span className="font-bold text-orange-300">tech.anand</span>
              <span className="text-orange-400/70">technician</span>
              <span className="px-2 py-1 bg-orange-600/50 text-orange-200 rounded text-xs">tech</span>
            </div>
            <div className="flex justify-between items-center bg-red-800/30 p-3 rounded-lg border border-red-400/20">
              <span className="font-bold text-red-300">admin.sys</span>
              <span className="text-red-400/70">admin</span>
              <span className="px-2 py-1 bg-red-600/50 text-red-200 rounded text-xs">admin</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
