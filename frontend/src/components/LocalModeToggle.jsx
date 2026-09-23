import { Cloud, HardDrive } from 'lucide-react';
import { useLocalMode } from '../context/LocalModeContext';
import './LocalModeToggle.css';

// S3 Task 4: explicit, always-visible indicator of whether this session hits
// external APIs (Groq) or is local-only. Lives in the sidebar footer so it's
// visible on every screen, not just Verify-a-Filing. Toggling it is a real
// behavior switch (see LocalModeContext.jsx, documents.py, citations.py) --
// draft generation reroutes to local Ollama; citation verification is
// honestly disabled with an explanation, since its entailment check is
// pinned to Groq by deliberate S2 design.
const LocalModeToggle = () => {
    const { localOnly, toggleLocalOnly } = useLocalMode();

    return (
        <button
            type="button"
            className={`local-mode-toggle ${localOnly ? 'local' : 'cloud'}`}
            onClick={toggleLocalOnly}
            title={localOnly
                ? 'Local-only mode is ON — no Groq calls. Draft generation uses local Ollama; Verify-a-Filing is unavailable.'
                : 'Cloud mode — using Groq for drafting and citation verification. Click to switch to local-only.'}
        >
            {localOnly ? <HardDrive size={14} /> : <Cloud size={14} />}
            <span>{localOnly ? 'Local-only' : 'Cloud'}</span>
            <span className="local-mode-dot" />
        </button>
    );
};

export default LocalModeToggle;
