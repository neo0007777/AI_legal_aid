import { Circle, Loader2, CheckCircle2, MinusCircle, HelpCircle } from 'lucide-react';
import './PipelineStageList.css';

// Generic backend-truthful pipeline stage checklist. Every row is driven by a
// real SSE {type: "stage", stage, status} event from the server -- pending
// until a "started" event arrives, in-progress until "done"/"skipped", never
// a client-side timer. Used by Verify Filing (via CitationStageList), AI Legal
// Aid, and Draft Assistant so the same transparency reads identically everywhere.
const PipelineStageList = ({ stages, stageOrder, stageLabels, title }) => {
    return (
        <div className="stage-list">
            {title && <div className="stage-list-title">{title}</div>}
            {stageOrder.map((key) => {
                const s = stages?.[key];
                const status = s?.status || 'pending';
                let Icon = Circle;
                let cls = 'pending';
                if (status === 'started') { Icon = Loader2; cls = 'in-progress'; }
                else if (status === 'done') { Icon = CheckCircle2; cls = 'done'; }
                else if (status === 'skipped') { Icon = MinusCircle; cls = 'skipped'; }
                else if (status === 'unknown') { Icon = HelpCircle; cls = 'unknown'; }

                return (
                    <div key={key} className={`stage-row ${cls}`}>
                        <Icon size={15} className={status === 'started' ? 'spin' : ''} />
                        <span className="stage-label">{stageLabels[key] || key}</span>
                        {status === 'skipped' && s?.reason && <span className="stage-reason">— {s.reason}</span>}
                        {status === 'unknown' && <span className="stage-reason">— couldn't confirm</span>}
                    </div>
                );
            })}
        </div>
    );
};

export default PipelineStageList;
