// Mirrors backend/app/models/schemas.py

export type Platform = "youtube" | "instagram" | "x";

export interface MediaFormat {
  id: string;
  label: string;
  kind: "video" | "audio" | "image";
  container: string | null;
  width: number | null;
  height: number | null;
  bitrate: number | null;
  filesize: number | null;
  derived: boolean;
  available: boolean;
  unavailable_reason: string | null;
}

export type DownloadReason =
  | "allowed"
  | "platform_prohibits"
  | "not_connected"
  | "not_owner"
  | "copyright_withheld"
  | "sign_in_required"
  | "platform_not_configured"
  | "no_media";

export interface DownloadEligibility {
  allowed: boolean;
  reason: DownloadReason;
  message: string;
  action: "connect" | "sign_in" | "open_external" | null;
  action_url: string | null;
}

export interface MediaInfo {
  platform: Platform;
  media_id: string;
  canonical_url: string;
  title: string | null;
  author: string | null;
  thumbnail_url: string | null;
  duration_seconds: number | null;
  published_at: string | null;
  media_type: string | null;
}

export interface AnalyzeResponse {
  media: MediaInfo;
  formats: MediaFormat[];
  download: DownloadEligibility;
  notices: string[];
}

export type JobStatus =
  | "queued"
  | "downloading"
  | "processing"
  | "uploading"
  | "completed"
  | "failed"
  | "cancelled"
  | "expired";

export interface Job {
  id: string;
  platform: Platform;
  media_id: string;
  format_id: string;
  status: JobStatus;
  progress: number | null;
  error_code: string | null;
  error_message: string | null;
  download_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface DownloadLink {
  download_id: string;
  url: string;
  filename: string;
  content_type: string;
  size_bytes: number | null;
  expires_in: number;
  file_expires_at: string;
}

export interface ConnectionInfo {
  platform: Platform;
  configured: boolean;
  connectable: boolean;
  connected: boolean;
  account_name: string | null;
  connected_at: string | null;
  note: string | null;
}

export interface PlatformStatus {
  platform: Platform;
  enabled: boolean;
  configured: boolean;
  missing: string[];
  capabilities: Record<string, boolean>;
  summary: string;
}

export interface AdminOverview {
  window_hours: number;
  requests_total: number;
  analyze_total: number;
  jobs_completed: number;
  jobs_failed: number;
  jobs_active: number;
  queue_depth: number;
  oldest_queued_seconds: number | null;
  by_platform: Record<string, Record<string, number>>;
  recent_errors: { id: string; platform: string; error_code: string; error_message: string; finished_at: string }[];
}

export interface AdminUser {
  id: string;
  email: string | null;
  role: "user" | "admin";
  is_blocked: boolean;
  created_at: string;
  jobs_7d: number;
}

export interface RateLimitConfig {
  analyze_per_minute: number;
  jobs_per_minute: number;
  max_active_jobs_per_user: number;
}
