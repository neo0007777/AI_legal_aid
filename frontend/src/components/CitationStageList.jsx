import { Circle, Loader2, CheckCircle2, MinusCircle } from 'lucide-react';
import './CitationStageList.css';

// Harness-sprint Part B: the actual named pipeline stages, in the order they
// really run. This mirrors backend/services/citation_verifier.py's emit()
// calls exactly -- if a stage genuinely runs, it's started/done; if
// correction memory short-circuits (or resolution fails), stages 2-4 are
// marked skipped with the real reason, never faked as instant.
const STAGE_ORDER = ['checking_correction_memory', 'resolving_citation', 'retrieving_judgment', 'running_entailment', 'applying_verdict'];

const STAGE_LABELS = {
    checking_correction_memory: 'Checking correction memory',
    resolving_citation: 'Resolving citation',
    retrieving_judgment: 'Retrieving judgment',
    running_entailment: 'Running entailment check',
    applying_verdict: 'Applying verdict',
};

const CitationStageList = ({ stages, caseName }) => {
    return (
        <div className="stage-list">
            {caseName && <div className="stage-list-title">{caseName}</div>}
            {STAGE_ORDER.map((key) => {
                const s = stages?.[key];
                const status = s?.status || 'pending';
                let Icon = Circle;
                let cls = 'pending';
                if (status === 'started') { Icon = Loader2; cls = 'in-progress'; }
                else if (status === 'done') { Icon = CheckCircle2; cls = 'done'; }
                else if (status === 'skipped') { Icon = MinusCircle; cls = 'skipped'; }

                return (
                    <div key={key} className={`stage-row ${cls}`}>
                        <Icon size={15} className={status === 'started' ? 'spin' : ''} />
                        <span className="stage-label">{STAGE_LABELS[key]}</span>
                        {status === 'skipped' && s.reason && <span className="stage-reason">— {s.reason}</span>}
                    </div>
                );
            })}
        </div>
    );
};

export default CitationStageList;
