"use client";

import { useEffect, useState } from "react";

import { ApiError, getCurrentUser } from "@/lib/api/client";
import type { CurrentUser } from "@/lib/api/types";

export type CurrentUserState =
  | { status: "loading" }
  | { status: "unauthenticated" }
  | { status: "error"; message: string }
  | { status: "authenticated"; user: CurrentUser };

export function useCurrentUser(): CurrentUserState {
  const [state, setState] = useState<CurrentUserState>({ status: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    getCurrentUser(controller.signal)
      .then((user) => setState({ status: "authenticated", user }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        if (error instanceof ApiError && error.status === 401) {
          setState({ status: "unauthenticated" });
          return;
        }
        setState({
          status: "error",
          message: error instanceof Error ? error.message : "Não foi possível carregar seus dados.",
        });
      });
    return () => controller.abort();
  }, []);

  return state;
}
