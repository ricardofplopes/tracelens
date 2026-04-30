"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Upload, Link, Loader2, AlertCircle, Images } from "lucide-react";

export default function HomePage() {
  const router = useRouter();
  const [dragActive, setDragActive] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [batchFiles, setBatchFiles] = useState<File[]>([]);
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState<string | null>(null);
  const [batchMode, setBatchMode] = useState(false);
  const [batchResult, setBatchResult] = useState<{ created: number; failed: number; jobs: { job_id: string; source: string }[]; errors: { source: string; error: string }[] } | null>(null);

  const handleFile = useCallback((f: File) => {
    setFile(f);
    setBatchFiles([]);
    setBatchMode(false);
    setUrl("");
    setError("");
    setBatchResult(null);
    const reader = new FileReader();
    reader.onload = (e) => setPreview(e.target?.result as string);
    reader.readAsDataURL(f);
  }, []);

  const handleMultipleFiles = useCallback((files: FileList) => {
    if (files.length === 1) {
      handleFile(files[0]);
      return;
    }
    setBatchMode(true);
    setBatchFiles(Array.from(files));
    setFile(null);
    setPreview(null);
    setUrl("");
    setError("");
    setBatchResult(null);
  }, [handleFile]);

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setDragActive(false);
      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        handleMultipleFiles(e.dataTransfer.files);
      }
    },
    [handleMultipleFiles]
  );

  const handleSubmit = async () => {
    if (!file && !url && batchFiles.length === 0) {
      setError("Please upload an image or provide a URL");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const API_BASE = "";

      // Batch mode: multiple files
      if (batchMode && batchFiles.length > 0) {
        const formData = new FormData();
        batchFiles.forEach((f) => formData.append("files", f));

        const res = await fetch(`${API_BASE}/api/jobs/batch`, {
          method: "POST",
          body: formData,
        });

        if (!res.ok) {
          const errText = await res.text();
          throw new Error(errText);
        }

        const result = await res.json();
        setBatchResult(result);
        setLoading(false);

        // If only one succeeded, navigate directly
        if (result.jobs.length === 1) {
          router.push(`/jobs/${result.jobs[0].job_id}`);
        }
        return;
      }

      // Single mode
      const formData = new FormData();
      if (file) {
        formData.append("file", file);
      }
      if (url) {
        formData.append("source_url", url);
      }

      const res = await fetch(`${API_BASE}/api/jobs`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const errText = await res.text();
        throw new Error(errText);
      }

      const job = await res.json();
      router.push(`/jobs/${job.id}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to create job");
      setLoading(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto">
      <div className="text-center mb-10">
        <h1 className="text-4xl font-semibold mb-3 pb-1 bg-gradient-to-r from-indigo-400 via-purple-400 to-fuchsia-400 bg-clip-text text-transparent leading-normal tracking-tight">
          Image Investigation
        </h1>
        <p className="text-gray-400 text-lg font-light tracking-wide">
          Upload an image to analyze it with AI and search across multiple reverse image search engines
        </p>
      </div>

      {/* Upload Zone */}
      <div
        className={`relative border-2 border-dashed rounded-2xl p-12 text-center transition-all cursor-pointer
          ${dragActive
            ? "border-blue-400 bg-blue-400/10"
            : "border-gray-700 hover:border-gray-500 bg-gray-900/50"
          }`}
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
        onClick={() => document.getElementById("file-input")?.click()}
      >
        <input
          id="file-input"
          type="file"
          accept="image/*"
          multiple
          className="hidden"
          onChange={(e) => {
            if (e.target.files && e.target.files.length > 0) {
              handleMultipleFiles(e.target.files);
            }
          }}
        />

        {batchMode && batchFiles.length > 0 ? (
          <div className="space-y-4">
            <Images className="w-12 h-12 mx-auto text-indigo-400" />
            <p className="text-lg text-gray-300">
              {batchFiles.length} images selected for batch investigation
            </p>
            <div className="flex flex-wrap gap-2 justify-center">
              {batchFiles.slice(0, 8).map((f, i) => (
                <span key={i} className="text-xs bg-gray-800 text-gray-400 px-2 py-1 rounded">
                  {f.name}
                </span>
              ))}
              {batchFiles.length > 8 && (
                <span className="text-xs text-gray-500">+{batchFiles.length - 8} more</span>
              )}
            </div>
            <button
              onClick={(e) => {
                e.stopPropagation();
                setBatchFiles([]);
                setBatchMode(false);
              }}
              className="text-sm text-red-400 hover:text-red-300"
            >
              Clear all
            </button>
          </div>
        ) : preview ? (
          <div className="space-y-4">
            <img
              src={preview}
              alt="Preview"
              className="max-h-64 mx-auto rounded-lg shadow-lg"
            />
            <p className="text-sm text-gray-400">{file?.name}</p>
            <button
              onClick={(e) => {
                e.stopPropagation();
                setFile(null);
                setPreview(null);
              }}
              className="text-sm text-red-400 hover:text-red-300"
            >
              Remove
            </button>
          </div>
        ) : (
          <div className="space-y-4">
            <Upload className="w-12 h-12 mx-auto text-gray-500" />
            <div>
              <p className="text-lg text-gray-300">
                Drop images here or click to upload
              </p>
              <p className="text-sm text-gray-500 mt-1">
                Supports JPEG, PNG, GIF, WebP (max 50MB) &bull; Select multiple for batch
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Divider */}
      <div className="flex items-center my-6">
        <div className="flex-1 border-t border-gray-800" />
        <span className="px-4 text-sm text-gray-500">OR</span>
        <div className="flex-1 border-t border-gray-800" />
      </div>

      {/* URL Input */}
      <div className="flex gap-3">
        <div className="flex-1 relative">
          <Link className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-500" />
          <input
            type="url"
            placeholder="Paste image URL..."
            value={url}
            onChange={(e) => {
              setUrl(e.target.value);
              setFile(null);
              setPreview(null);
              setBatchFiles([]);
              setBatchMode(false);
              setError("");
              setBatchResult(null);
            }}
            className="w-full pl-10 pr-4 py-3 bg-gray-900 border border-gray-700 rounded-xl text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
          />
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="mt-4 p-3 bg-red-900/30 border border-red-800 rounded-lg flex items-center gap-2 text-red-300 text-sm">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          {error}
        </div>
      )}

      {/* Batch Result */}
      {batchResult && (
        <div className="mt-4 p-4 bg-gray-900/80 border border-gray-700 rounded-xl space-y-3">
          <p className="text-sm text-gray-300">
            <span className="text-green-400 font-medium">{batchResult.created} investigations started</span>
            {batchResult.failed > 0 && (
              <span className="text-red-400 ml-2">({batchResult.failed} failed)</span>
            )}
          </p>
          <div className="space-y-2">
            {batchResult.jobs.map((j) => (
              <a
                key={j.job_id}
                href={`/jobs/${j.job_id}`}
                className="block text-sm text-indigo-400 hover:text-indigo-300 truncate"
              >
                → {j.source}
              </a>
            ))}
          </div>
          {batchResult.errors.length > 0 && (
            <div className="text-xs text-red-400 space-y-1">
              {batchResult.errors.map((e, i) => (
                <p key={i}>{e.source}: {e.error}</p>
              ))}
            </div>
          )}
          <a href="/jobs" className="inline-block text-sm text-gray-400 hover:text-gray-300 mt-2">
            View all investigations →
          </a>
        </div>
      )}

      {/* Submit */}
      <button
        onClick={handleSubmit}
        disabled={loading || (!file && !url && batchFiles.length === 0)}
        className="mt-6 w-full py-3 px-6 bg-indigo-600 hover:bg-indigo-500 disabled:bg-gray-800 disabled:text-gray-500 text-white font-medium rounded-xl transition-all flex items-center justify-center gap-2 shadow-lg shadow-indigo-600/20 hover:shadow-indigo-500/30"
      >
        {loading ? (
          <>
            <Loader2 className="w-5 h-5 animate-spin" />
            {batchMode ? "Starting Batch Investigation..." : "Starting Investigation..."}
          </>
        ) : (
          <>
            {batchMode ? <Images className="w-5 h-5" /> : <Upload className="w-5 h-5" />}
            {batchMode ? `Investigate ${batchFiles.length} Images` : "Investigate Image"}
          </>
        )}
      </button>

      {/* How it works */}
      <div className="mt-12 grid grid-cols-1 md:grid-cols-3 gap-6">
        {[
          {
            title: "🔬 Analyze",
            desc: "AI vision analysis, OCR, metadata extraction, and perceptual hashing",
          },
          {
            title: "🌐 Search",
            desc: "Query multiple reverse image search engines simultaneously",
          },
          {
            title: "📊 Report",
            desc: "Aggregated results with confidence scoring and AI synthesis",
          },
        ].map((item) => (
          <div
            key={item.title}
            className="p-5 bg-gray-900/50 border border-gray-800 rounded-xl"
          >
            <h3 className="text-lg font-semibold mb-2">{item.title}</h3>
            <p className="text-sm text-gray-400">{item.desc}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
