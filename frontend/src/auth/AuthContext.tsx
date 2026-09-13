import {
  createContext,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import * as authApi from "../api/auth";
import { attemptSilentRefresh, setAuthLostHandler } from "../api/client";
import type { User } from "../types";

interface AuthContextValue {
  user: User | null;
  ready: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (params: {
    email: string;
    password: string;
    fullName?: string;
    inviteCode?: string;
  }) => Promise<void>;
  logout: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);

  // Stays false until the silent refresh settles, so a page reload does not
  // flash the login screen at an already-signed-in user.
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const restore = async () => {
      const token = await attemptSilentRefresh();

      if (token) {
        const profile = await authApi.me().catch(() => null);

        if (!cancelled) {
          setUser(profile);
        }
      }

      if (!cancelled) {
        setReady(true);
      }
    };

    void restore();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    setAuthLostHandler(() => setUser(null));

    return () => setAuthLostHandler(null);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const response = await authApi.login(email, password);
    setUser(response.user);
  }, []);

  const register = useCallback(
    async (params: {
      email: string;
      password: string;
      fullName?: string;
      inviteCode?: string;
    }) => {
      const response = await authApi.register(params);
      setUser(response.user);
    },
    [],
  );

  const logout = useCallback(async () => {
    await authApi.logout();
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, ready, login, register, logout }),
    [user, ready, login, register, logout],
  );

  return (
    <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
  );
}
