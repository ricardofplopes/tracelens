const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface Job {
  id: string;
  status: string;
  image_source: string;
  source_url: string | null;
  original_filename: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface Asset {
  id: string;
  variant: string;
  file_path: string;
  width: number | null;
  height: number | null;
  mime_type: string | null;
  file_size: number | null;
}

export interface Feature {
  sha256: string | null;
  phash: string | null;
  dhash: string | null;
  ahash: string | null;
  color_histogram: Record<string, number[]> | null;
  orb_descriptor_count: number | null;
  dimensions: string | null;
  mime_type: string | null;
  exif_data: Record<string, unknown> | null;
  ocr_text: string | null;
}

export interface CandidateResult {
  id: string;
  provider_name: string;
  source_url: string | null;
  page_title: string | null;
  thumbnail_url: string | null;
  match_type: string;
  similarity_score: number | null;
  confidence: number | null;
  extracted_text: string | null;
  metadata: Record<string, unknown> | null;
}

export interface ProviderRun {
  id: string;
  provider_name: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  error_message: string | null;
  result_count: number;
}

export interface Report {
  summary: string | null;
  ai_description: string | null;
  entities: Record<string, string[]> | null;
  search_terms: Record<string, string[]> | null;
  cluster_count: number;
  top_matches: Record<string, unknown[]> | null;
  created_at: string | null;
}

export interface JobDetail {
  job: Job;
  assets: Asset[];
  features: Feature | null;
  provider_runs: ProviderRun[];
  report: Report | null;
}

export interface JobResults {
  job_id: string;
  status: string;
  candidates: CandidateResult[];
  report: Report | null;
  provider_runs: ProviderRun[];
}

export interface ProviderInfo {
  name: string;
  enabled: boolean;
  experimental: boolean;
  description: string;
}

export interface HealthStatus {
  status: string;
  database: boolean;
  redis: boolean;
  ollama: boolean;
}

async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      ...options?.headers,
    },
  });
  if (!res.ok) {
    const error = await res.text();
    throw new Error(`API error ${res.status}: ${error}`);
  }
  return res.json();
}

export async function createJob(file?: File, sourceUrl?: string): Promise<Job> {
  const formData = new FormData();
  if (file) {
    formData.append("file", file);
  }
  if (sourceUrl) {
    formData.append("source_url", sourceUrl);
  }
  return fetchApi<Job>("/api/jobs", {
    method: "POST",
    body: formData,
  });
}

export async function getJob(jobId: string): Promise<JobDetail> {
  return fetchApi<JobDetail>(`/api/jobs/${jobId}`);
}

export async function getJobResults(jobId: string): Promise<JobResults> {
  return fetchApi<JobResults>(`/api/jobs/${jobId}/results`);
}

export async function getProviders(): Promise<ProviderInfo[]> {
  return fetchApi<ProviderInfo[]>("/api/providers");
}

export async function testProviders(): Promise<unknown[]> {
  return fetchApi<unknown[]>("/api/providers/test", { method: "POST" });
}

export async function getHealth(): Promise<HealthStatus> {
  return fetchApi<HealthStatus>("/api/health");
}

export function getAssetUrl(filePath: string): string {
  // Convert file path to URL: /app/uploads/xxx -> /uploads/xxx
  const relative = filePath.replace(/^\/app\/uploads/, "/uploads");
  return `${API_BASE}${relative}`;
}
