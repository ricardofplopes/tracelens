"use client";

import { useState, useEffect, useCallback } from "react";
import { useParams } from "next/navigation";
import {
  Loader2, CheckCircle, XCircle, Clock, Search,
  ExternalLink, Filter, ChevronDown, ChevronUp, Eye
} from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Job {
  id: string;
  status: string;
  image_source: string;
  source_url: string | null;
  original_filename: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

interface Asset {
  id: string;
  variant: string;
  file_path: string;
  width: number | null;
  height: number | null;
}

interface Feature {
  sha256: string | null;
  phash: string | null;
  dhash: string | null;
  ahash: string | null;
  dimensions: string | null;
  mime_type: string | null;
  ocr_text: string | null;
  exif_data: Record<string, unknown> | null;
  orb_descriptor_count: number | null;
}

interface CandidateResult {
  id: string;
  provider_name: string;
  source_url: string | null;
  page_title: string | null;
  thumbnail_url: string | null;
  match_type: string;
  similarity_score: number | null;
  confidence: number | null;
  extracted_text: string | null;
}

interface ProviderRun {
  id: string;
  provider_name: string;
  status: string;
  result_count: number;
  error_message: string | null;
}

interface Report {
  summary: string | null;
  ai_description: string | null;
  entities: { entities?: string[]; brands?: string[]; landmarks?: string[] } | null;
  search_terms: { terms?: string[] } | null;
  cluster_count: number;
}

const STATUS_STEPS = [
  { key: "pending", label: "Queued" },
  { key: "ingesting", label: "Ingesting" },
  { key: "extracting", label: "Extracting Features" },
  { key: "analyzing", label: "AI Analysis" },
  { key: "searching", label: "Searching Providers" },
  { key: "scoring", label: "Scoring Results" },
  { key: "reporting", label: "Generating Report" },
  { key: "complete", label: "Complete" },
];

function getAssetUrl(filePath: string): string {
  const relative = filePath.replace(/^\/app\/uploads/, "/uploads");
  return `${API_BASE}${relative}`;
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    pending: "bg-yellow-900/50 text-yellow-300 border-yellow-700",
    complete: "bg-green-900/50 text-green-300 border-green-700",
    failed: "bg-red-900/50 text-red-300 border-red-700",
    success: "bg-green-900/50 text-green-300 border-green-700",
  };
  const color = colors[status] || "bg-blue-900/50 text-blue-300 border-blue-700";
  return (
    <span className={`px-2 py-0.5 text-xs rounded-full border ${color}`}>
      {status}
    </span>
  );
}

function ConfidenceBadge({ confidence }: { confidence: number | null }) {
  if (confidence === null) return null;
  const pct = Math.round(confidence * 100);
  let color = "text-red-400";
  if (pct >= 70) color = "text-green-400";
  else if (pct >= 40) color = "text-yellow-400";
  return <span className={`font-mono font-bold ${color}`}>{pct}%</span>;
}

function MatchTypeBadge({ type }: { type: string }) {
  const colors: Record<string, string> = {
    exact: "bg-green-900/50 text-green-300 border-green-700",
    similar: "bg-blue-900/50 text-blue-300 border-blue-700",
    text: "bg-purple-900/50 text-purple-300 border-purple-700",
    entity: "bg-orange-900/50 text-orange-300 border-orange-700",
  };
  return (
    <span className={`px-2 py-0.5 text-xs rounded-full border ${colors[type] || colors.similar}`}>
      {type}
    </span>
  );
}

export default function JobPage() {
  const params = useParams();
  const jobId = params.id as string;

  const [job, setJob] = useState<Job | null>(null);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [features, setFeatures] = useState<Feature | null>(null);
  const [candidates, setCandidates] = useState<CandidateResult[]>([]);
  const [providerRuns, setProviderRuns] = useState<ProviderRun[]>([]);
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState("");
  const [filterProvider, setFilterProvider] = useState<string>("all");
  const [filterType, setFilterType] = useState<string>("all");
  const [showFeatures, setShowFeatures] = useState(false);
  const [showReport, setShowReport] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      const [detailRes, resultsRes] = await Promise.all([
        fetch(`${API_BASE}/api/jobs/${jobId}`),
        fetch(`${API_BASE}/api/jobs/${jobId}/results`),
      ]);

      if (detailRes.ok) {
        const detail = await detailRes.json();
        setJob(detail.job);
        setAssets(detail.assets);
        setFeatures(detail.features);
        setProviderRuns(detail.provider_runs);
        setReport(detail.report);
      }

      if (resultsRes.ok) {
        const results = await resultsRes.json();
        setCandidates(results.candidates || []);
        if (results.report) setReport(results.report);
        if (results.provider_runs) setProviderRuns(results.provider_runs);
      }
    } catch (err) {
      setError("Failed to load job data");
    }
  }, [jobId]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(() => {
      if (job?.status && !["complete", "failed"].includes(job.status)) {
        fetchData();
      }
    }, 3000);
    return () => clearInterval(interval);
  }, [fetchData, job?.status]);

  const currentStepIdx = STATUS_STEPS.findIndex((s) => s.key === job?.status);
  const isProcessing = job?.status && !["complete", "failed"].includes(job.status);

  const filteredCandidates = candidates.filter((c) => {
    if (filterProvider !== "all" && c.provider_name !== filterProvider) return false;
    if (filterType !== "all" && c.match_type !== filterType) return false;
    return true;
  });

  const providerNames = Array.from(new Set(candidates.map((c) => c.provider_name)));
  const matchTypes = Array.from(new Set(candidates.map((c) => c.match_type)));

  const originalAsset = assets.find((a) => a.variant === "original");

  if (error) {
    return (
      <div className="text-center py-20">
        <XCircle className="w-12 h-12 mx-auto text-red-400 mb-4" />
        <p className="text-red-300">{error}</p>
      </div>
    );
  }

  if (!job) {
    return (
      <div className="text-center py-20">
        <Loader2 className="w-8 h-8 mx-auto animate-spin text-blue-400" />
        <p className="text-gray-400 mt-4">Loading...</p>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold">Investigation</h1>
          <p className="text-sm text-gray-500 mt-1 font-mono">{job.id}</p>
        </div>
        <StatusBadge status={job.status} />
      </div>

      {/* Progress Steps */}
      {isProcessing && (
        <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-6">
          <div className="flex items-center justify-between">
            {STATUS_STEPS.map((step, idx) => {
              const isActive = idx === currentStepIdx;
              const isDone = idx < currentStepIdx;
              return (
                <div key={step.key} className="flex items-center">
                  <div className="flex flex-col items-center">
                    <div
                      className={`w-8 h-8 rounded-full flex items-center justify-center text-sm
                        ${isDone ? "bg-green-600 text-white" : ""}
                        ${isActive ? "bg-blue-600 text-white animate-pulse" : ""}
                        ${!isDone && !isActive ? "bg-gray-800 text-gray-500" : ""}
                      `}
                    >
                      {isDone ? <CheckCircle className="w-4 h-4" /> : idx + 1}
                    </div>
                    <span
                      className={`text-xs mt-1 ${isActive ? "text-blue-400" : isDone ? "text-green-400" : "text-gray-600"}`}
                    >
                      {step.label}
                    </span>
                  </div>
                  {idx < STATUS_STEPS.length - 1 && (
                    <div className={`w-8 h-0.5 mx-1 ${isDone ? "bg-green-600" : "bg-gray-800"}`} />
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Image + Features */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Original Image */}
        <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-gray-400 mb-3">Original Image</h3>
          {originalAsset && (
            <img
              src={getAssetUrl(originalAsset.file_path)}
              alt="Original"
              className="w-full rounded-lg"
            />
          )}
          {job.original_filename && (
            <p className="text-xs text-gray-500 mt-2 truncate">{job.original_filename}</p>
          )}
          {job.source_url && (
            <p className="text-xs text-gray-500 mt-1 truncate">{job.source_url}</p>
          )}
        </div>

        {/* Features Panel */}
        <div className="lg:col-span-2 bg-gray-900/50 border border-gray-800 rounded-xl p-4">
          <button
            onClick={() => setShowFeatures(!showFeatures)}
            className="flex items-center justify-between w-full text-sm font-semibold text-gray-400"
          >
            <span>Extracted Features</span>
            {showFeatures ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>
          {showFeatures && features && (
            <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
              {features.sha256 && (
                <div>
                  <span className="text-gray-500">SHA-256:</span>
                  <p className="font-mono text-xs text-gray-300 break-all">{features.sha256}</p>
                </div>
              )}
              {features.phash && (
                <div>
                  <span className="text-gray-500">pHash:</span>
                  <p className="font-mono text-xs text-gray-300">{features.phash}</p>
                </div>
              )}
              {features.dhash && (
                <div>
                  <span className="text-gray-500">dHash:</span>
                  <p className="font-mono text-xs text-gray-300">{features.dhash}</p>
                </div>
              )}
              {features.ahash && (
                <div>
                  <span className="text-gray-500">aHash:</span>
                  <p className="font-mono text-xs text-gray-300">{features.ahash}</p>
                </div>
              )}
              {features.dimensions && (
                <div>
                  <span className="text-gray-500">Dimensions:</span>
                  <p className="text-gray-300">{features.dimensions}</p>
                </div>
              )}
              {features.mime_type && (
                <div>
                  <span className="text-gray-500">MIME:</span>
                  <p className="text-gray-300">{features.mime_type}</p>
                </div>
              )}
              {features.orb_descriptor_count !== null && (
                <div>
                  <span className="text-gray-500">ORB Keypoints:</span>
                  <p className="text-gray-300">{features.orb_descriptor_count}</p>
                </div>
              )}
              {features.ocr_text && (
                <div className="col-span-2">
                  <span className="text-gray-500">OCR Text:</span>
                  <p className="text-gray-300 text-xs mt-1 bg-gray-800 p-2 rounded whitespace-pre-wrap">
                    {features.ocr_text}
                  </p>
                </div>
              )}
            </div>
          )}
          {showFeatures && !features && (
            <p className="text-gray-500 text-sm mt-4">Features not yet extracted</p>
          )}
        </div>
      </div>

      {/* AI Report */}
      {report && (
        <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-6">
          <button
            onClick={() => setShowReport(!showReport)}
            className="flex items-center justify-between w-full"
          >
            <h3 className="text-lg font-semibold flex items-center gap-2">
              <Eye className="w-5 h-5 text-purple-400" />
              AI Investigation Report
            </h3>
            {showReport ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
          </button>
          {showReport && (
            <div className="mt-4 space-y-4">
              {report.summary && (
                <div className="prose prose-invert prose-sm max-w-none">
                  <p className="text-gray-300 whitespace-pre-wrap">{report.summary}</p>
                </div>
              )}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
                {report.entities?.entities && report.entities.entities.length > 0 && (
                  <div>
                    <span className="text-gray-500">Entities:</span>
                    <div className="flex flex-wrap gap-1 mt-1">
                      {report.entities.entities.map((e: string, i: number) => (
                        <span key={i} className="px-2 py-0.5 bg-blue-900/30 text-blue-300 rounded text-xs">{e}</span>
                      ))}
                    </div>
                  </div>
                )}
                {report.entities?.brands && report.entities.brands.length > 0 && (
                  <div>
                    <span className="text-gray-500">Brands:</span>
                    <div className="flex flex-wrap gap-1 mt-1">
                      {report.entities.brands.map((b: string, i: number) => (
                        <span key={i} className="px-2 py-0.5 bg-orange-900/30 text-orange-300 rounded text-xs">{b}</span>
                      ))}
                    </div>
                  </div>
                )}
                {report.entities?.landmarks && report.entities.landmarks.length > 0 && (
                  <div>
                    <span className="text-gray-500">Landmarks:</span>
                    <div className="flex flex-wrap gap-1 mt-1">
                      {report.entities.landmarks.map((l: string, i: number) => (
                        <span key={i} className="px-2 py-0.5 bg-green-900/30 text-green-300 rounded text-xs">{l}</span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
              <div className="text-sm text-gray-500">
                {report.cluster_count} unique result clusters found
              </div>
            </div>
          )}
        </div>
      )}

      {/* Provider Status */}
      {providerRuns.length > 0 && (
        <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-gray-400 mb-3">Provider Status</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {providerRuns.map((pr) => (
              <div key={pr.id} className="flex items-center justify-between p-2 bg-gray-800/50 rounded-lg">
                <div>
                  <p className="text-sm font-medium">{pr.provider_name}</p>
                  <p className="text-xs text-gray-500">{pr.result_count} results</p>
                </div>
                <StatusBadge status={pr.status} />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Filters */}
      {candidates.length > 0 && (
        <div className="flex items-center gap-4 flex-wrap">
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-gray-500" />
            <span className="text-sm text-gray-400">Filters:</span>
          </div>
          <select
            value={filterProvider}
            onChange={(e) => setFilterProvider(e.target.value)}
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-300"
          >
            <option value="all">All Providers</option>
            {providerNames.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-300"
          >
            <option value="all">All Types</option>
            {matchTypes.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
          <span className="text-sm text-gray-500">
            {filteredCandidates.length} of {candidates.length} results
          </span>
        </div>
      )}

      {/* Results Grid */}
      {filteredCandidates.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {filteredCandidates.map((c) => (
            <div
              key={c.id}
              className="bg-gray-900/50 border border-gray-800 rounded-xl p-4 hover:border-gray-700 transition-colors"
            >
              <div className="flex items-start gap-3">
                {c.thumbnail_url && (
                  <img
                    src={c.thumbnail_url}
                    alt=""
                    className="w-20 h-20 object-cover rounded-lg flex-shrink-0 bg-gray-800"
                    onError={(e) => {
                      (e.target as HTMLImageElement).style.display = "none";
                    }}
                  />
                )}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <MatchTypeBadge type={c.match_type} />
                    <span className="text-xs text-gray-500">{c.provider_name}</span>
                    <div className="ml-auto">
                      <ConfidenceBadge confidence={c.confidence} />
                    </div>
                  </div>
                  <h4 className="text-sm font-medium truncate">
                    {c.page_title || "Untitled"}
                  </h4>
                  {c.source_url && (
                    <a
                      href={c.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1 mt-1 truncate"
                    >
                      <ExternalLink className="w-3 h-3 flex-shrink-0" />
                      <span className="truncate">{c.source_url}</span>
                    </a>
                  )}
                  {c.extracted_text && (
                    <p className="text-xs text-gray-500 mt-2 line-clamp-2">
                      {c.extracted_text}
                    </p>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Empty state */}
      {job.status === "complete" && candidates.length === 0 && (
        <div className="text-center py-12">
          <Search className="w-12 h-12 mx-auto text-gray-600 mb-4" />
          <p className="text-gray-400">No matches found across any providers</p>
        </div>
      )}

      {/* Error state */}
      {job.status === "failed" && (
        <div className="bg-red-900/20 border border-red-800 rounded-xl p-6 text-center">
          <XCircle className="w-12 h-12 mx-auto text-red-400 mb-4" />
          <p className="text-red-300 font-medium">Investigation Failed</p>
          {job.error_message && (
            <p className="text-red-400/70 text-sm mt-2">{job.error_message}</p>
          )}
        </div>
      )}
    </div>
  );
}
