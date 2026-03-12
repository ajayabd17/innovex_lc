"use client";

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type { RunStatus } from "@/types/api";

export type RunHistoryEntry = {
  run_id: string;
  company_name: string;
  status: RunStatus;
  timestamp: string;
};

type RunHistoryState = {
  runs: RunHistoryEntry[];
  upsertRun: (entry: RunHistoryEntry) => void;
  removeRun: (runId: string) => void;
  clear: () => void;
};

export const useRunHistoryStore = create<RunHistoryState>()(
  persist(
    (set, get) => ({
      runs: [],
      upsertRun: (entry) => {
        const runs = get().runs.filter((r) => r.run_id !== entry.run_id);
        runs.unshift(entry);
        set({ runs: runs.slice(0, 30) });
      },
      removeRun: (runId) => set({ runs: get().runs.filter((r) => r.run_id !== runId) }),
      clear: () => set({ runs: [] }),
    }),
    {
      name: "innovex-run-history",
      storage: createJSONStorage(() => sessionStorage),
    },
  ),
);
