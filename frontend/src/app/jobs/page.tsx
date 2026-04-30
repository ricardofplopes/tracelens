"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  Loader2, CheckCircle, XCircle, Clock, Search,
  ChevronLeft, ChevronRight, ImageIcon, Globe, Trash2,
} from "lucide-react";

const API_BASE = "";

interface Job {
  id: string;
  status: string;
  image_source: string;
  source_url: string | null;
  original_filename: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  thumbnail: string | null;
}

interface JobsResponse {
  jobs: Job[];
  total: number;
  page: number;
  pages: number;
}

function StatusBadge({ status }: { status: string }) {
  const config: Record<string, { icon: React.ReactNode; label: string; className: string }> = {
    complete: {
      icon: <CheckCircle className="w-3.5 h-3.5" />,
      label: "Complete",
      className: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
    },
    failed: {
      icon: <XCircle className="w-3.5 h-3.5" />,
      label: "Failed",
      className: "bg-red-500/10 text-red-400 border-red-500/20",
    },
    pending: {
      icon: <Clock className="w-3.5 h-3.5" />,
      label: "Pending",
      className: "bg-yellow-500/10 text-yellow-400 border-yellow-500/20",
    },
  };

  const fallback = {
    icon: <Loader2 className="w-3.5 h-3.5 animate-spin" />,
    label: status.charAt(0).toUpperCase() + status.slice(1),
    className: "bg-blue-500/10 text-blue-400 border-blue-500/20",
  };

  const { icon, label, className } = config[status] || fallback;

  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full border ${className}`}>
      {icon}
      {label}
    </span>
  );
}

export default function JobsPage() {
  const router = useRouter();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [statusFilter, setStatusFilter] = useState<string>("");

  const fetchJobs = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page: String(page), limit: "20" });
      if (statusFilter) params.set("status", statusFilter);
      const res = await fetch(`${API_BASE}/api/jobs?${params}`);
      if (!res.ok) throw new Error("Failed to fetch jobs");
      const data: JobsResponse = await res.json();
      setJobs(data.jobs);
      setPages(data.pages);
      setTotal(data.total);
    } catch {
      setJobs([]);
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter]);

  useEffect(() => {
    fetchJobs();
  }, [fetchJobs]);

  useEffect(() => {
    setPage(1);
  }, [statusFilter]);

  const formatDate = (iso: string) => {
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, {
      month: "short", day: "numeric", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  };

  const getThumbnail = (job: Job) => {
    if (job.thumbnail) return `${API_BASE}${job.thumbnail}`;
    return null;
  };

  const handleDelete = async (jobId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm("Delete this investigation? This cannot be undone.")) return;
    try {
      await fetch(`${API_BASE}/api/jobs/${jobId}`, { method: "DELETE" });
      fetchJobs();
    } catch {
      // Ignore errors
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Investigation History</h1>
          <p className="text-sm text-gray-400 mt-1">
            {total} total investigation{total !== 1 ? "s" : ""}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="bg-gray-900/50 border border-gray-800 text-sm text-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          >
            <option value="">All Statuses</option>
            <option value="complete">Complete</option>
            <option value="failed">Failed</option>
            <option value="pending">Pending</option>
            <option value="ingesting">Ingesting</option>
            <option value="extracting">Extracting</option>
            <option value="analyzing">Analyzing</option>
            <option value="searching">Searching</option>
            <option value="scoring">Scoring</option>
            <option value="reporting">Reporting</option>
          </select>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-8 h-8 animate-spin text-indigo-400" />
        </div>
      ) : jobs.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <Search className="w-12 h-12 text-gray-600 mb-4" />
          <h2 className="text-lg font-medium text-gray-400">No investigations found</h2>
          <p className="text-sm text-gray-500 mt-1">
            {statusFilter ? "Try a different status filter or " : ""}
            <a href="/" className="text-indigo-400 hover:text-indigo-300">start a new investigation</a>
          </p>
        </div>
      ) : (
        <>
          <div className="bg-gray-900/50 border border-gray-800 rounded-xl overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-800">
                  <th className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider px-4 py-3">Image</th>
                  <th className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider px-4 py-3">Source</th>
                  <th className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider px-4 py-3">Status</th>
                  <th className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider px-4 py-3">Created</th>
                  <th className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider px-4 py-3 w-12"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800/50">
                {jobs.map((job) => {
                  const thumb = getThumbnail(job);
                  return (
                    <tr
                      key={job.id}
                      onClick={() => router.push(`/jobs/${job.id}`)}
                      className="hover:bg-white/[0.02] cursor-pointer transition-colors"
                    >
                      <td className="px-4 py-3">
                        {thumb ? (
                          <img
                            src={thumb}
                            alt=""
                            className="w-10 h-10 rounded-md object-cover border border-gray-700"
                          />
                        ) : (
                          <div className="w-10 h-10 rounded-md bg-gray-800 border border-gray-700 flex items-center justify-center">
                            <ImageIcon className="w-4 h-4 text-gray-500" />
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          {job.image_source === "url" ? (
                            <Globe className="w-4 h-4 text-gray-500 flex-shrink-0" />
                          ) : (
                            <ImageIcon className="w-4 h-4 text-gray-500 flex-shrink-0" />
                          )}
                          <span className="text-sm text-gray-300 truncate max-w-[300px]">
                            {job.original_filename || job.source_url || "Unknown source"}
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge status={job.status} />
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-400">
                        {formatDate(job.created_at)}
                      </td>
                      <td className="px-4 py-3">
                        <button
                          onClick={(e) => handleDelete(job.id, e)}
                          className="p-1.5 rounded-md text-gray-500 hover:text-red-400 hover:bg-red-400/10 transition-colors"
                          title="Delete investigation"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {pages > 1 && (
            <div className="flex items-center justify-between">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="inline-flex items-center gap-1.5 px-3 py-2 text-sm text-gray-400 hover:text-white bg-gray-900/50 border border-gray-800 rounded-lg disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronLeft className="w-4 h-4" />
                Previous
              </button>
              <span className="text-sm text-gray-400">
                Page {page} of {pages}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(pages, p + 1))}
                disabled={page >= pages}
                className="inline-flex items-center gap-1.5 px-3 py-2 text-sm text-gray-400 hover:text-white bg-gray-900/50 border border-gray-800 rounded-lg disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Next
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
