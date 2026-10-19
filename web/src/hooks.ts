import { useCallback, useEffect, useRef, useState } from "react";
import { imageUrl } from "./api";

/** Load data and refetch every `refreshMs` (optional). Errors are exposed, never thrown into render. */
export function useLoad<T>(fn: () => Promise<T>, deps: unknown[], refreshMs?: number) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  const reload = useCallback(async () => {
    try {
      setData(await fnRef.current());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    setLoading(true);
    void reload();
    if (!refreshMs) return;
    const t = setInterval(() => void reload(), refreshMs);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reload, refreshMs, ...deps]);

  return { data, error, loading, reload };
}

/** Authenticated image -> blob URL, revoked on change/unmount. `version` forces a refetch. */
export function useImage(path: string | null, version?: unknown) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    let made: string | null = null;
    setUrl(null);
    if (path) {
      void imageUrl(path).then((u) => {
        if (!live) {
          if (u) URL.revokeObjectURL(u);
          return;
        }
        made = u;
        setUrl(u);
      });
    }
    return () => {
      live = false;
      if (made) URL.revokeObjectURL(made);
    };
  }, [path, version]);
  return url;
}
