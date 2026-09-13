import type { TokenResponse, User } from "../types";
import { request, setAccessToken } from "./client";

export async function login(
  email: string,
  password: string,
): Promise<TokenResponse> {
  const response = await request<TokenResponse>("/api/auth/login", {
    method: "POST",
    body: { email, password },
    skipRefresh: true,
  });

  setAccessToken(response.access_token);

  return response;
}

export async function register(params: {
  email: string;
  password: string;
  fullName?: string;
  inviteCode?: string;
}): Promise<TokenResponse> {
  const response = await request<TokenResponse>("/api/auth/register", {
    method: "POST",
    body: {
      email: params.email,
      password: params.password,
      full_name: params.fullName || null,
      invite_code: params.inviteCode || null,
    },
    skipRefresh: true,
  });

  setAccessToken(response.access_token);

  return response;
}

export async function logout(): Promise<void> {
  await request<void>("/api/auth/logout", {
    method: "POST",
    skipRefresh: true,
  }).catch(() => undefined);

  setAccessToken(null);
}

export function me(): Promise<User> {
  return request<User>("/api/auth/me");
}
