import { createPortal } from 'react-dom';
import { X, AlertTriangle, Quote, RefreshCw } from 'lucide-react';
import './ContradictionDiff.css';

// S3 Task 3: an actual side-by-side comparison, not a text dump. The one-line
// entailment.reasoning is the lede (surfaced first, large) so a first-time
// viewer sees WHY it's a mismatch before reading either full passage.
const ContradictionDiff = ({ citation, onClose }) => {
    if (!citation) return null;

    const rawClaim = citation.claimed_content || citation.context_snippet;
    const claim = typeof rawClaim === 'string' ? rawClaim : (rawClaim ? JSON.stringify(rawClaim) : '(no claim text captured)');
    const rawSource = citation.proposition_verification?.evidence_passage || citation.matched_text;
    const source = typeof rawSource === 'string' ? rawSource : (rawSource ? JSON.stringify(rawSource) : null);
    const rawReasoning = citation.proposition_verification?.reasoning || citation.entailment?.reasoning;
    const reasoning = typeof rawReasoning === 'string' ? rawReasoning : (rawReasoning ? JSON.stringify(rawReasoning) : '');
    const verdict = citation.proposition_verification?.verdict || citation.entailment?.verdict || 'unclear';
    const caseName = citation.matched_case?.case_name || citation.case_name;
    // technical_failure: the entailment CALL failed (rate limit, timeout) --
    // this is not a real contradiction finding, so it must never be framed as
    // one. Caught in UX audit: a raw Groq error string (with a billing URL)
    // was rendered in this exact modal as if it were the model's reasoning.
    const technicalFailure = citation.entailment?.technical_failure;

    // Portal straight to <body>: this page wraps its content in an
    // .animate-fade-in ancestor, and a completed CSS transform (even a
    // no-op translateY(0) left by animation-fill-mode: forwards) creates a
    // new containing block for position:fixed descendants -- without the
    // portal, this modal renders positioned against the scrolled page
    // instead of the viewport (confirmed via bounding-box inspection in
    // browser testing: it rendered ~800px above the visible viewport).
    return createPortal((
        <div className="diff-modal-overlay" onClick={onClose}>
            <div className="diff-modal" onClick={(e) => e.stopPropagation()}>
                <div className="diff-modal-header">
                    <div>
                        <span className="diff-eyebrow">
                            {technicalFailure ? <RefreshCw size={14} /> : <AlertTriangle size={14} />}
                            {technicalFailure ? 'Verification Incomplete' : 'Contradiction Detail'}
                        </span>
                        <h3>{caseName}</h3>
                    </div>
                    <button className="diff-close-btn outline" onClick={onClose}><X size={18} /></button>
                </div>

                {technicalFailure ? (
                    <div className="diff-technical-failure-panel">
                        <p>
                            This citation could not actually be checked — the verification service was
                            temporarily unavailable. This is <strong>not</strong> a confirmed contradiction, just
                            an incomplete check. Please retry verification.
                        </p>
                    </div>
                ) : reasoning && (
                    <div className="diff-reasoning-callout">
                        <Quote size={16} className="diff-quote-icon" />
                        <p>{reasoning}</p>
                    </div>
                )}

                <div className="diff-split-grid">
                    <div className="diff-pane diff-pane-claim">
                        <h5>What the filing claims</h5>
                        <div className="diff-text-box claim">{claim}</div>
                    </div>
                    <div className="diff-pane diff-pane-source">
                        <h5>What the source judgment actually says</h5>
                        <div className="diff-text-box source">
                            {source || 'No passage was retrieved for this case to compare against.'}
                        </div>
                    </div>
                </div>

                <div className="diff-verdict-footer">
                    Model verdict: <strong>{verdict}</strong>
                    {citation.paragraph_display && <span> · {citation.paragraph_display}</span>}
                </div>
            </div>
        </div>
    ), document.body);
};

export default ContradictionDiff;
