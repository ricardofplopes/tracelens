"use client";

import { useState, useEffect, useCallback } from "react";
import { Settings, CheckCircle, XCircle, Loader2, RefreshCw } from "lucide-react";

const API_BASE = "";

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

interface OllamaModel {
  name: string;
  size: number;
  modified_at: string;
  details: Record<string, unknown>;
}

interface SystemInfo {
  disk: { total_gb: number; used_gb: number; free_gb: number; usage_percent: number } | null;
  uploads: { file_count: number; total_size_mb: number };
}

interface TestResult {
  healthy: boolean;
  message: string;
  latency_ms: number | null;
}

function StatusDot({ ok }: { ok: boolean }) {
  return (
    <span className={`inline-block w-2 h-2 rounded-full ${ok ? "bg-green-400" : "bg-red-400"}`} />
  );
}

function TimeAgo({ date }: { date: Date }) {
  const [seconds, setSeconds] = useState(0);

  useEffect(() => {
    const update = () => setSeconds(Math.floor((Date.now() - date.getTime()) / 1000));
    update();
    const interval = setInterval(update, 1000);
    return () => clearInterval(interval);
  }, [date]);

  return <span className="text-xs text-gray-500">Last checked: {seconds}s ago</span>;
}

export default function SettingsPage() {
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [testing, setTesting] = useState(false);
  const [testResults, setTestResults] = useState<Record<string, TestResult>>({});
  const [models, setModels] = useState<OllamaModel[]>([]);
  const [currentVision, setCurrentVision] = useState("");
  const [currentText, setCurrentText] = useState("");
  const [systemInfo, setSystemInfo] = useState<SystemInfo | null>(null);
  const [lastChecked, setLastChecked] = useState<Date | null>(null);

  const fetchHealth = useCallback(() => {
    fetch(`${API_BASE}/api/health`)
      .then((r) => r.json())
      .then((data) => {
        setHealth(data);
        setLastChecked(new Date());
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    fetch(`${API_BASE}/api/providers`)
      .then((r) => r.json())
      .then(setProviders)
      .catch(() => {});

    fetchHealth();

    fetch(`${API_BASE}/api/system/info`)
      .then((r) => r.json())
      .then(setSystemInfo)
      .catch(() => {});

    fetch(`${API_BASE}/api/ollama/models`)
      .then((r) => r.json())
      .then((data) => {
        setModels(data.models || []);
        setCurrentVision(data.current_vision_model || "");
        setCurrentText(data.current_text_model || "");
      })
      .catch(() => {});
  }, [fetchHealth]);

  const runTests = async () => {
    setTesting(true);
    try {
      const res = await fetch(`${API_BASE}/api/providers/test`, { method: "POST" });
      const results = await res.json();
      const map: Record<string, TestResult> = {};
      for (const r of results) {
        map[r.name] = { healthy: r.healthy, message: r.message, latency_ms: r.latency_ms };
      }
      setTestResults(map);
      setLastChecked(new Date());
    } catch {
      // ignore
    }
    setTesting(false);
  };

  const sortedProviders = [...providers].sort((a, b) => {
    const la = testResults[a.name]?.latency_ms ?? Infinity;
    const lb = testResults[b.name]?.latency_ms ?? Infinity;
    return la - lb;
  });

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      <div className="flex items-center gap-3">
        <Settings className="w-6 h-6 text-gray-400" />
        <h1 className="text-2xl font-bold">Settings</h1>
      </div>

      {/* System Health */}
      <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">System Health</h2>
          <div className="flex items-center gap-3">
            {lastChecked && <TimeAgo date={lastChecked} />}
            <button
              onClick={fetchHealth}
              className="p-1.5 bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors"
              title="Refresh health status"
            >
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
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

      {/* System Resources */}
      {systemInfo && (
        <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-6">
          <h2 className="text-lg font-semibold mb-4">System Resources</h2>
          <div className="space-y-4">
            {systemInfo.disk && (
              <div>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-gray-400">Disk Usage</span>
                  <span className="text-gray-300">
                    {systemInfo.disk.used_gb} / {systemInfo.disk.total_gb} GB ({systemInfo.disk.usage_percent}%)
                  </span>
                </div>
                <div className="w-full h-2 bg-gray-800 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full ${
                      systemInfo.disk.usage_percent > 90
                        ? "bg-red-500"
                        : systemInfo.disk.usage_percent > 70
                          ? "bg-yellow-500"
                          : "bg-indigo-500"
                    }`}
                    style={{ width: `${systemInfo.disk.usage_percent}%` }}
                  />
                </div>
              </div>
            )}
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-gray-800/50 rounded-lg p-3">
                <p className="text-2xl font-bold">{systemInfo.uploads.file_count}</p>
                <p className="text-xs text-gray-400">Upload Files</p>
              </div>
              <div className="bg-gray-800/50 rounded-lg p-3">
                <p className="text-2xl font-bold">{systemInfo.uploads.total_size_mb} MB</p>
                <p className="text-xs text-gray-400">Storage Used</p>
              </div>
            </div>
          </div>
        </div>
      )}

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
          {sortedProviders.map((p) => (
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
                  <div className="flex items-center gap-2 mt-1">
                    {testResults[p.name].healthy ? (
                      <CheckCircle className="w-3 h-3 text-green-400" />
                    ) : (
                      <XCircle className="w-3 h-3 text-red-400" />
                    )}
                    <span className="text-xs text-gray-500">{testResults[p.name].message}</span>
                    {testResults[p.name].latency_ms != null && (
                      <span
                        className={`text-xs font-mono ${
                          testResults[p.name].latency_ms! < 500
                            ? "text-green-400"
                            : testResults[p.name].latency_ms! < 2000
                              ? "text-yellow-400"
                              : "text-red-400"
                        }`}
                      >
                        {testResults[p.name].latency_ms}ms
                      </span>
                    )}
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

      {/* Ollama Models */}
      <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-6">
        <h2 className="text-lg font-semibold mb-4">Ollama Models</h2>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-4">
            <div className="p-3 bg-gray-800/50 rounded-lg">
              <p className="text-xs text-gray-500 mb-1">Vision Model</p>
              <p className="text-sm font-medium">{currentVision || "Not configured"}</p>
            </div>
            <div className="p-3 bg-gray-800/50 rounded-lg">
              <p className="text-xs text-gray-500 mb-1">Text Model</p>
              <p className="text-sm font-medium">{currentText || "Not configured"}</p>
            </div>
          </div>

          {models.length > 0 && (
            <div>
              <p className="text-sm text-gray-400 mb-2">Available Models</p>
              <div className="space-y-2">
                {models.map((m) => (
                  <div
                    key={m.name}
                    className="flex items-center justify-between p-3 bg-gray-800/50 rounded-lg"
                  >
                    <span className="text-sm font-medium">{m.name}</span>
                    <span className="text-xs text-gray-500">
                      {m.size > 1e9
                        ? `${(m.size / 1e9).toFixed(1)} GB`
                        : `${(m.size / 1e6).toFixed(0)} MB`}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
        <p className="text-xs text-gray-600 mt-4">
          Model selection is configured via OLLAMA_VISION_MODEL and OLLAMA_TEXT_MODEL in .env
        </p>
      </div>
    </div>
  );
}
