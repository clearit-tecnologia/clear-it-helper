"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { getReadiness } from "@/lib/api/client";
import type { ReadinessResponse } from "@/lib/api/types";

export const READINESS_INTERVAL_MS = 15_000;

export interface ReadinessState {
  data: ReadinessResponse | null;
  error: string | null;
  isLoading: boolean;
  isRefreshing: boolean;
  lastUpdated: Date | null;
  refresh: () => void;
}

export function useReadiness(intervalMs: number = READINESS_INTERVAL_MS): ReadinessState {
  const [data, setData] = useState<ReadinessResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setIsRefreshing(true);
    try {
      const result = await getReadiness(controller.signal);
      setData(result);
      setError(null);
      setLastUpdated(new Date());
    } catch (err) {
      if (controller.signal.aborted) return;
      setError(err instanceof Error ? err.message : "Não foi possível consultar o status do ambiente.");
      setLastUpdated(new Date());
    } finally {
      if (!controller.signal.aborted) {
        setIsLoading(false);
        setIsRefreshing(false);
      }
    }
  }, []);

  useEffect(() => {
    void load();
    const id = window.setInterval(() => {
      // Não consulta enquanto a aba está em segundo plano.
      if (document.visibilityState !== "hidden") void load();
    }, intervalMs);
    return () => {
      window.clearInterval(id);
      controllerRef.current?.abort();
    };
  }, [load, intervalMs]);

  const refresh = useCallback(() => {
    void load();
  }, [load]);

  return { data, error, isLoading, isRefreshing, lastUpdated, refresh };
}
