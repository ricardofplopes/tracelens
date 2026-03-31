"use client";

import { useState, useEffect } from "react";
import { Settings, CheckCircle, XCircle, Loader2, RefreshCw } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface ProviderInfo {
  name: string;
  enabled: boolean;
  experimental: boolean;
  description: string;
}

interface HealthStatus {
  status: string;
  database: boolean;
  redis: boolean;
  ollama: boolean;
}

function StatusDot({ ok }: { ok: boolean }) {
  return (
    <span className={`inline-block w-2 h-2 rounded-full ${ok ? "bg-green-400" : "bg-red-400"}`} />
  );
}

export default function SettingsPage() {
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [testing, setTesting] = useState(false);
  const [testResults, setTestResults] = useState<Record<string, { healthy: boolean; message: string }>>({});

  useEffect(() => {
    fetch(`${API_BASE}/api/providers`)
      .then((r) => r.json())
      .then(setProviders)
      .catch(() => {});

    fetch(`${API_BASE}/api/health`)
      .then((r) => r.json())
      .then(setHealth)
      .catch(() => {});
  }, []);

  const runTests = async () => {
    setTesting(true);
    try {
      const res = await fetch(`${API_BASE}/api/providers/test`, { method: "POST" });
      const results = await res.json();
      const map: Record<string, { healthy: boolean; message: string }> = {};
      for (const r of results) {
        map[r.name] = { healthy: r.healthy, message: r.message };
      }
      setTestResults(map);
    } catch {
      // ignore
    }
    setTesting(false);
  };

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      <div className="flex items-center gap-3">
        <Settings className="w-6 h-6 text-gray-400" />
        <h1 className="text-2xl font-bold">Settings</h1>
      </div>

      {/* System Health */}
      <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-6">
        <h2 className="text-lg font-semibold mb-4">System Health</h2>
        {health ? (
          <div className="grid grid-cols-3 gap-4">
            <div className="flex items-center gap-2">
              <StatusDot ok={health.database} />
              <span className="text-sm">Database</span>
            </div>
            <div className="flex items-center gap-2">
              <StatusDot ok={health.redis} />
              <span className="text-sm">Redis</span>
            </div>
            <div className="flex items-center gap-2">
              <StatusDot ok={health.ollama} />
              <span className="text-sm">Ollama</span>
            </div>
          </div>
        ) : (
          <p className="text-gray-500 text-sm">Loading...</p>
        )}
      </div>

      {/* Providers */}
      <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">Search Providers</h2>
          <button
            onClick={runTests}
            disabled={testing}
            className="flex items-center gap-2 px-3 py-1.5 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm transition-colors"
          >
            {testing ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <RefreshCw className="w-4 h-4" />
            )}
            Test All
          </button>
        </div>

        <div className="space-y-3">
          {providers.map((p) => (
            <div
              key={p.name}
              className="flex items-center justify-between p-3 bg-gray-800/50 rounded-lg"
            >
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">{p.name}</span>
                  {p.experimental && (
                    <span className="px-1.5 py-0.5 text-xs bg-yellow-900/50 text-yellow-300 border border-yellow-700 rounded">
                      experimental
                    </span>
                  )}
                </div>
                <p className="text-xs text-gray-500 mt-0.5">{p.description}</p>
                {testResults[p.name] && (
                  <div className="flex items-center gap-1 mt-1">
                    {testResults[p.name].healthy ? (
                      <CheckCircle className="w-3 h-3 text-green-400" />
                    ) : (
                      <XCircle className="w-3 h-3 text-red-400" />
                    )}
                    <span className="text-xs text-gray-500">{testResults[p.name].message}</span>
                  </div>
                )}
              </div>
              <div
                className={`px-2 py-1 rounded text-xs font-medium ${
                  p.enabled
                    ? "bg-green-900/30 text-green-300"
                    : "bg-gray-700 text-gray-400"
                }`}
              >
                {p.enabled ? "Enabled" : "Disabled"}
              </div>
            </div>
          ))}
        </div>
        <p className="text-xs text-gray-600 mt-4">
          Provider settings are configured via environment variables in .env
        </p>
      </div>

      {/* Ollama Config Info */}
      <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-6">
        <h2 className="text-lg font-semibold mb-4">Ollama Configuration</h2>
        <div className="space-y-2 text-sm">
          <p className="text-gray-400">
            Configure Ollama models via environment variables:
          </p>
          <div className="bg-gray-800 rounded-lg p-3 font-mono text-xs space-y-1">
            <p><span className="text-blue-400">OLLAMA_HOST</span>=http://ollama:11434</p>
            <p><span className="text-blue-400">OLLAMA_VISION_MODEL</span>=llava</p>
            <p><span className="text-blue-400">OLLAMA_TEXT_MODEL</span>=llama3.2</p>
          </div>
          <p className="text-gray-500 text-xs mt-3">
            Pull models with: <code className="bg-gray-800 px-1 rounded">docker compose exec ollama ollama pull llava</code>
          </p>
        </div>
      </div>
    </div>
  );
}
