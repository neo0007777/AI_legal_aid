import { CheckCircle2, AlertTriangle, HelpCircle, SignalHigh, SignalMedium, SignalLow, RefreshCw } from 'lucide-react';
import './CitationStatusBadge.css';

// UX Consistency Pass item 1: three DISTINCT visual states, one color scheme,
// used identically everywhere in the app. "Not found" never implies fraud —
// it means outside the indexed corpus, full stop, both in this label and
// everywhere else in the frontend that touches citation status.
export const STATUS_META = {
    'Verified': { className: 'verified', label: 'Verified', Icon: CheckCircle2 },
    'Mismatch': { className: 'mismatch', label: 'Mismatch', Icon: AlertTriangle },
    'Not found in indexed corpus': { className: 'not-found', label: 'Not found in indexed corpus', Icon: HelpCircle },
};

export const getStatusMeta = (status) => STATUS_META[status] || STATUS_META['Not found in indexed corpus'];

const CitationStatusBadge = ({ status, size = 14 }) => {
    const { className, label, Icon } = getStatusMeta(status);
    return (
        <span className={`citation-status-badge ${className}`}>
            <Icon size={size} /> {label}
        </span>
    );
};

export default CitationStatusBadge;

// Deliberately NOT reusing the green/amber/grey status color system here — a
// citation can be a confident Mismatch (the model correctly, confidently
// caught a contradiction), so pairing "confidence" with the same color
// meaning as "status" would visually contradict itself. Signal-strength bars
// in neutral ink keep the two indicators legible side by side.
export const ConfidenceBars = ({ confidence }) => {
    const level = { high: 3, medium: 2, low: 1 }[confidence] || 0;
    const Icon = level === 3 ? SignalHigh : level === 2 ? SignalMedium : SignalLow;
    return (
        <span className="confidence-bars" title={`Model confidence: ${confidence || 'unknown'}`}>
            <Icon size={14} /> {confidence ? `${confidence} confidence` : 'confidence unknown'}
        </span>
    );
};

// Distinguishes "we checked and it's a Mismatch" from "we couldn't check right
// now" -- caught in UX audit: a rate-limited/timed-out entailment call was
// labeled with a plain "Mismatch" badge indistinguishable from a genuine,
// confident contradiction finding. technical_failure=true (set by the backend
// only when the entailment CALL itself failed, never when the model actually
// evaluated the passage) renders this instead of implying a real finding.
export const TechnicalFailureNote = () => (
    <span className="technical-failure-note">
        <RefreshCw size={13} /> Verification service was unavailable — this result is incomplete, please retry
    </span>
);
