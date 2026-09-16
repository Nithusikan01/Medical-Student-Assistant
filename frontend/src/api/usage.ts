import type { ModelUsageResponse } from "../types";
import { request } from "./client";

export function getModelUsage(): Promise<ModelUsageResponse> {
  return request<ModelUsageResponse>("/api/usage/models");
}
