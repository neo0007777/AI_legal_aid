import { useCallback, useRef, useState } from 'react';

// Same SSE line-framing VerifyFiling.jsx already uses to consume
// verify-filing's stream -- one JSON event per "data: ...\n\n" chunk.
async function* readSSE(response) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = buffer.indexOf('\n\n')) !== -1) {
            const chunk = buffer.slice(0, idx);
            buffer = buffer.slice(idx + 2);
            const line = chunk.split('\n').find((l) => l.startsWith('data: '));
            if (line) {
                try { yield JSON.parse(line.slice(6)); } catch { /* skip malformed chunk */ }
            }
        }
    }
}

const MIN_IN_PROGRESS_MS = 300;

// Drives a fetch() that returns an SSE stream of {type: "stage", stage, status}
// events (plus a single terminal "done" or "error" event), and turns them into
// a `stages` map for <PipelineStageList>. Every transition comes from a real
// server event -- the only client-side timing here is a floor so a stage that
// starts and finishes within 300ms still visibly shows its in-progress frame,
// never a fabricated stage that didn't actually run.
export function useStageStream() {
    const [stages, setStages] = useState({});
    const [connectionLost, setConnectionLost] = useState(false);
    const timersRef = useRef({});

    const reset = useCallback(() => {
        Object.values(timersRef.current).forEach(clearTimeout);
        timersRef.current = {};
        setStages({});
        setConnectionLost(false);
    }, []);

    const applyStageEvent = useCallback((event) => {
        const { stage, status, reason } = event;
        if (status === 'started') {
            setStages((prev) => ({ ...prev, [stage]: { status: 'started', startedAt: Date.now() } }));
            return;
        }
        setStages((prev) => {
            const existing = prev[stage];
            const elapsed = existing?.startedAt ? Date.now() - existing.startedAt : MIN_IN_PROGRESS_MS;
            if (existing?.status === 'started' && elapsed < MIN_IN_PROGRESS_MS) {
                clearTimeout(timersRef.current[stage]);
                timersRef.current[stage] = setTimeout(() => {
                    setStages((p) => ({ ...p, [stage]: { status, reason } }));
                }, MIN_IN_PROGRESS_MS - elapsed);
                return prev;
            }
            return { ...prev, [stage]: { status, reason } };
        });
    }, []);

    // fetchPromise: the in-flight fetch() call. onDone/onError receive the
    // terminal event's payload; stage events are handled internally.
    const run = useCallback(async (fetchPromise, { onDone, onError } = {}) => {
        reset();
        let sawTerminal = false;
        try {
            const response = await fetchPromise;
            if (!response.ok) {
                let msg = 'Request failed';
                try { const e = await response.json(); msg = e.detail || msg; } catch { msg = `Server error (${response.status})`; }
                throw new Error(msg);
            }
            for await (const event of readSSE(response)) {
                if (event.type === 'stage') {
                    applyStageEvent(event);
                } else if (event.type === 'done') {
                    sawTerminal = true;
                    onDone?.(event);
                } else if (event.type === 'error') {
                    sawTerminal = true;
                    onError?.(event.message || 'Something went wrong.');
                }
            }
            if (!sawTerminal) {
                setConnectionLost(true);
                onError?.("Connection ended before a result arrived — couldn't confirm progress. Result may still be correct if it was already saved.");
            }
        } catch (err) {
            setConnectionLost(true);
            onError?.(err.message);
        }
    }, [applyStageEvent, reset]);

    return { stages, connectionLost, run, reset };
}
