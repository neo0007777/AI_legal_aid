import { useState } from 'react';
import { ChevronLeft, ChevronRight, FlagOff, ExternalLink } from 'lucide-react';
import CitationStatusBadge, { ConfidenceBars, TechnicalFailureNote } from './CitationStatusBadge';
import './CitationWalkthrough.css';

// S3 Task 2: section-by-section navigation. Reuses S2's citation data directly
// (one citation = one "section") -- no new backend work. Confidence and
// status are both visible without scrolling, back/forward works, and the
// final step signals "end of document" per the acceptance test.
const CitationWalkthrough = ({ citations, onOpenDiff }) => {
    const [index, setIndex] = useState(0);
    const total = citations.length;
    const citation = citations[index];
    const isLast = index === total - 1;
    const isFirst = index === 0;

    if (total === 0) return null;

    const caseName = citation.matched_case?.case_name || citation.case_name;

    return (
        <div className="walkthrough-shell animate-fade-in">
            <div className="walkthrough-progress">
                Section {index + 1} of {total}
                <div className="walkthrough-progress-track">
                    <div className="walkthrough-progress-fill" style={{ width: `${((index + 1) / total) * 100}%` }} />
                </div>
            </div>

            <div className="walkthrough-card">
                <div className="walkthrough-card-top">
                    <CitationStatusBadge status={citation.status} size={15} />
                    {citation.entailment?.confidence && !citation.entailment?.technical_failure && (
                        <ConfidenceBars confidence={citation.entailment.confidence} />
                    )}
                </div>
                {citation.entailment?.technical_failure && <TechnicalFailureNote />}

                <h3>{caseName}</h3>
                {citation.matched_case && (
                    <p className="walkthrough-meta">
                        {citation.matched_case.court} · {citation.matched_case.date?.slice(0, 10)}
                        {citation.paragraph_display ? ` · ${citation.paragraph_display}` : ''}
                    </p>
                )}

                <div className="walkthrough-claim">
                    <h6>Claimed in the filing</h6>
                    <p>{citation.claimed_content || citation.context_snippet}</p>
                </div>

                {citation.status === 'Not found in indexed corpus' && (
                    <p className="walkthrough-not-found-note">
                        No matching source in our indexed corpus — this doesn't mean the citation is fake,
                        only that it falls outside our current Supreme Court, 2016–2025 coverage.
                    </p>
                )}

                {citation.status === 'Mismatch' && (
                    <button className="outline walkthrough-diff-btn" onClick={() => onOpenDiff(citation)}>
                        <ExternalLink size={15} /> {citation.entailment?.technical_failure ? 'View details' : 'View contradiction'}
                    </button>
                )}
            </div>

            <div className="walkthrough-nav">
                <button className="outline" disabled={isFirst} onClick={() => setIndex(i => i - 1)}>
                    <ChevronLeft size={16} /> Back
                </button>
                {isLast ? (
                    <div className="walkthrough-end-signal">
                        <FlagOff size={16} /> End of document — {total} citation{total !== 1 ? 's' : ''} reviewed
                    </div>
                ) : (
                    <button onClick={() => setIndex(i => i + 1)}>
                        Next <ChevronRight size={16} />
                    </button>
                )}
            </div>
        </div>
    );
};

export default CitationWalkthrough;
