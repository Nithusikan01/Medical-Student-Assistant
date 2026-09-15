import type { AdminUserSummary } from "../types";
import { request } from "./client";

export function listUsers(): Promise<AdminUserSummary[]> {
  return request<AdminUserSummary[]>("/api/users");
}

export function deleteUser(id: string, options?: { confirm?: boolean }): Promise<void> {
  const query = options?.confirm ? "?confirm=true" : "";
  return request<void>(`/api/users/${id}${query}`, { method: "DELETE" });
}

export function updateUserRole(
  id: string,
  role: "user" | "admin",
): Promise<AdminUserSummary> {
  return request<AdminUserSummary>(`/api/users/${id}/role`, {
    method: "PATCH",
    body: { role },
  });
}
