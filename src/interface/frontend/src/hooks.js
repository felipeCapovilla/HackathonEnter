import { useCallback, useEffect, useRef, useState } from "react";
import { request } from "./api";

export function useResource(path) {
  const [revision, setRevision] = useState(0);
  const [state, setState] = useState({ path: null, data: null, loading: false, error: "" });
  const reload = useCallback(() => setRevision((current) => current + 1), []);

  useEffect(() => {
    if (!path) return;
    let active = true;
    const controller = new AbortController();
    setState((current) => ({ path, data: current.path === path ? current.data : null, loading: true, error: "" }));
    request(path, { signal: controller.signal }).then((data) => {
      if (active) setState({ path, data, loading: false, error: "" });
    }).catch((error) => {
      if (active) setState((current) => ({ ...current, loading: false, error: error.message }));
    });
    return () => {
      active = false;
      controller.abort();
    };
  }, [path, revision]);

  return { ...(state.path === path ? state : { data: null, loading: Boolean(path), error: "" }), reload };
}

export function useAction() {
  const inFlight = useRef(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const run = useCallback(async (action) => {
    if (inFlight.current) return;
    inFlight.current = true;
    setPending(true);
    setError("");
    try {
      await action();
    } catch (cause) {
      setError(cause.message);
    } finally {
      inFlight.current = false;
      setPending(false);
    }
  }, []);
  return { pending, error, run };
}
