export type Project = {
  id: string;
  subject_name: string;
  title: string | null;
  status: string;
  role: string;
  media_count: number;
  default_language: string;
  created_at: string;
};
export type MediaAsset = {
  id: string;
  project_id: string;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  status: string;
  checksum_sha256: string | null;
  duration_ms: number | null;
  width: number | null;
  height: number | null;
  has_thumbnail: boolean;
  has_proxy: boolean;
  description: string | null;
  details: Record<string, unknown>;
  error: string | null;
  created_at: string;
};
export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/backend${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    if (response.status === 401 && typeof window !== "undefined")
      window.location.assign("/login");
    const data = await response
      .json()
      .catch(() => ({ detail: "The request failed. Please retry." }));
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : "Please check the submitted information.",
    );
  }
  return response.status === 204
    ? (undefined as T)
    : (response.json() as Promise<T>);
}
export function bytes(size: number) {
  return size < 1024 * 1024
    ? `${Math.max(1, Math.round(size / 1024))} KB`
    : `${(size / 1024 / 1024).toFixed(1)} MB`;
}
