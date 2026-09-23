import React, { createContext, useContext, useState, useEffect } from 'react';

const LocalModeContext = createContext();
export const useLocalMode = () => useContext(LocalModeContext);

// Explicit, always-visible local-only toggle (S3 Task 4). When on, draft
// generation is routed straight to the local Ollama fallback instead of
// Groq (see the X-Local-Only header threaded through in DraftAssistant and
// documents.py). Citation verification's entailment check is pinned to
// Groq's gpt-oss-120b by deliberate S2 design (no local fallback, accuracy-
// critical) -- so local-only mode honestly disables Verify-a-Filing with an
// explanation rather than silently degrading its accuracy guarantee.
export const LocalModeProvider = ({ children }) => {
    const [localOnly, setLocalOnly] = useState(() => {
        try {
            return localStorage.getItem('lexsetu_local_only') === 'true';
        } catch {
            return false;
        }
    });

    useEffect(() => {
        try {
            localStorage.setItem('lexsetu_local_only', String(localOnly));
        } catch { /* ignore */ }
    }, [localOnly]);

    return (
        <LocalModeContext.Provider value={{ localOnly, setLocalOnly, toggleLocalOnly: () => setLocalOnly(v => !v) }}>
            {children}
        </LocalModeContext.Provider>
    );
};
