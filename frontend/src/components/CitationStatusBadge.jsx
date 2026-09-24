import {
    CheckCircle2, AlertTriangle, HelpCircle, Search, WifiOff,
    SignalHigh, SignalMedium, SignalLow, RefreshCw, Globe, ShieldAlert,
    Check, X, Minus
} from 'lucide-react';
import './CitationStatusBadge.css';

// All possible top-level result states from the backend citation verifier.
export const STATUS_META = {
    'Verified': {
        className: 'verified',
        label: 'Verified',
        Icon: CheckCircle2,
    },
    'Partial Match': {
        className: 'partial',
        label: 'Partial Match',
        Icon: AlertTriangle,
    },
    'Mismatch': {
        className: 'mismatch',
        label: 'Mismatch',
        Icon: AlertTriangle,
    },
    'Possible Fabrication': {
        className: 'fabrication',
        label: 'Possible Fabrication',
        Icon: ShieldAlert,
    },
    'Unverified Citation': {
        className: 'unverified',
        label: 'Unverified Citation',
        Icon: HelpCircle,
    },
    'Not Indexed / Not Found': {
        className: 'not-found',
        label: 'Not Indexed / Not Found',
        Icon: HelpCircle,
    },
    'Not found in indexed corpus': {
        className: 'not-found',
        label: 'Not Indexed / Not Found',
        Icon: HelpCircle,
    },
    'External Source Error': {
        className: 'ext-error',
        label: 'Source Unavailable',
        Icon: WifiOff,
    },
};

export const getStatusMeta = (status) =>
    STATUS_META[status] || {
        className: 'not-found',
        label: status || 'Unknown',
        Icon: HelpCircle,
    };

const CitationStatusBadge = ({ status, size = 14 }) => {
    const { className, label, Icon } = getStatusMeta(status);
    return (
        <span className={`citation-status-badge ${className}`}>
            <Icon size={size} /> {label}
        </span>
    );
};

export default CitationStatusBadge;

// Identity status sub-badge for Stage 10 model
export const IdentityBadge = ({ status }) => {
    if (!status) return null;
    if (status === 'VERIFIED') {
        return (
            <span className="stage-sub-badge verified" title="Case identity canonicalized and verified against authoritative records">
                <Check size={11} strokeWidth={3} /> Identity: Verified
            </span>
        );
    }
    if (status === 'POSSIBLE_FABRICATION') {
        return (
            <span className="stage-sub-badge fabrication" title="No authoritative source record found after exhaustive search">
                <ShieldAlert size={11} /> Possible Fabrication
            </span>
        );
    }
    if (status === 'UNVERIFIED_CITATION') {
        return (
            <span className="stage-sub-badge unverified" title="Exact case authority could not be resolved from authoritative records">
                <HelpCircle size={11} /> Identity: Unverified
            </span>
        );
    }
    if (status === 'NOT_FOUND_IN_INDEXED_CORPUS') {
        return (
            <span className="stage-sub-badge not-run" title="Case not present in local Supreme Court indexed corpus">
                <Minus size={11} /> Not In Index
            </span>
        );
    }
    return (
        <span className="stage-sub-badge not-run">
            {status}
        </span>
    );
};

// Proposition status sub-badge for Stage 10 model
export const PropositionBadge = ({ status }) => {
    if (!status || status === 'NOT_RUN') {
        return (
            <span className="stage-sub-badge not-run" title="Proposition verification not run because case identity was not established">
                <Minus size={11} /> Proposition: Not Evaluated
            </span>
        );
    }
    if (status === 'SUPPORTED') {
        return (
            <span className="stage-sub-badge supported" title="The actual cited judgment directly supports this proposition">
                <Check size={11} strokeWidth={3} /> Proposition: Supported
            </span>
        );
    }
    if (status === 'PARTIALLY_SUPPORTED') {
        return (
            <span className="stage-sub-badge partial" title="The judgment supports the general principle but not the full claim">
                <AlertTriangle size={11} /> Proposition: Partially Supported
            </span>
        );
    }
    if (status === 'CONTRADICTED') {
        return (
            <span className="stage-sub-badge contradicted" title="The judgment explicitly contradicts the claimed proposition">
                <X size={11} strokeWidth={3} /> Proposition: Contradicted
            </span>
        );
    }
    return (
        <span className="stage-sub-badge mismatch" title="The actual judgment does not substantiate this proposition">
            <AlertTriangle size={11} /> Proposition: Not Supported
        </span>
    );
};

// Retrieval-source badge: shows WHERE the text came from
export const RetrievalSourceBadge = ({ retrievalSource, externalLookup }) => {
    if (retrievalSource === 'internal') {
        return (
            <span className="retrieval-source-badge internal" title="Text retrieved from local indexed corpus">
                <Search size={12} /> Indexed corpus
            </span>
        );
    }
    if (retrievalSource === 'external') {
        const source = externalLookup?.source || 'Indian Kanoon';
        return (
            <span className="retrieval-source-badge external" title={`Text retrieved from ${source}`}>
                <Globe size={12} /> {source}
            </span>
        );
    }
    return null;
};

// Confidence signal bars
export const ConfidenceBars = ({ confidence }) => {
    const level = { high: 3, medium: 2, low: 1 }[confidence] || 0;
    const Icon = level === 3 ? SignalHigh : level === 2 ? SignalMedium : SignalLow;
    return (
        <span className="confidence-bars" title={`Model confidence: ${confidence || 'unknown'}`}>
            <Icon size={14} /> {confidence ? `${confidence} confidence` : 'confidence unknown'}
        </span>
    );
};

// Distinguishes "we checked and it's a Mismatch" from "we couldn't check right now".
export const TechnicalFailureNote = () => (
    <span className="technical-failure-note">
        <RefreshCw size={13} /> Verification service was unavailable — this result is incomplete, please retry
    </span>
);
