import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
export type Row = { id: string; [key: string]: any };
export type Page = {
  items: Row[];
  total: number;
  page: number;
  page_size: number;
};
export type User = {
  id: string;
  full_name: string;
  email: string;
  role: string;
  permissions: string[];
  is_active: boolean;
};
export async function api<T = any>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await fetch("/api" + path, {
    method,
    credentials: "same-origin",
    headers: {
      "X-MIST-Request": "1",
      ...(body instanceof FormData
        ? {}
        : { "Content-Type": "application/json" }),
    },
    body:
      body === undefined
        ? undefined
        : body instanceof FormData
          ? body
          : JSON.stringify(body),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(
      error.detail?.message || `Request failed (${response.status})`,
    );
  }
  return response.json();
}
export function useData<T = any>(path: string, enabled = true) {
  return useQuery<T>({
    queryKey: [path],
    queryFn: () => api<T>(path),
    enabled,
    retry: false,
    refetchInterval:
      ["/outbox", "/campaigns", "/notifications", "/conversations", "/competitions", "/judge-directory", "/dashboard", "/tickets"].some(prefix => path.startsWith(prefix))
        ? 3000
        : false,
  });
}
export function useAction() {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: ({
      path,
      method = "POST",
      body,
    }: {
      path: string;
      method?: string;
      body?: unknown;
    }) => api(path, method, body),
    onSuccess: (_result, variables) => {
      if (variables.path === "/auth/logout") {
        cache.clear();
        window.location.assign("/login");
        return;
      }
      return cache.invalidateQueries();
    },
  });
}
const grants: Record<string, string[]> = {
  director: [
    "delete",
    "ticket_approve",
    "judges",
    "imports",
    "campaigns",
    "approve",
    "tickets",
    "catalogs",
    "audit",
    "users",
    "outbox",
    "jobs",
  ],
  technology_administrator: ["imports", "catalogs", "audit", "outbox", "jobs"],
  competitions_administrator: [
    "judges",
    "imports",
    "campaigns",
    "tickets",
    "catalogs",
    "outbox",
  ],
};
for (const role of ["competitions_administrator", "competitions_member", "competitions_chair"]) {
  grants[role] = ["judges", "imports", "campaigns", "approve", "tickets", "catalogs", "outbox"];
}
grants.competitions_chair.push("delete", "ticket_approve");
export function can(user: User | undefined, permission: string) {
  return (
    !!user &&
    (grants[user.role]?.includes(permission) ||
      (permission === "approve" &&
        user.permissions.includes("campaign_approver")) ||
      (permission === "tickets" &&
        user.permissions.includes("private_tickets")))
  );
}
export const label = (s: unknown) =>
  String(s === "waiting_on_organizer" ? "Awaiting organizer" : s ?? "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
export const date = (s: string | undefined) =>
  s ? new Date(s).toLocaleString() : "—";

export function requestId() {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join(
    "",
  );
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
