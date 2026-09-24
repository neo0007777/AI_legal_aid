import { useState } from 'react';
import { History } from 'lucide-react';
import './AdjustmentBadge.css';

// Harness-sprint Part A: "this must never be styled identically to a normal
// fresh verdict -- the whole point is that it's transparent, not invisible."
// Deliberately a different shape (dashed border, distinct color) from the
// green/amber/grey status pills, so it reads as an overlay ON a verdict, not
// as another verdict.
// interactive=false renders a plain, non-clickable tag -- used inside the
// citation-card-header <button>, where a nested interactive element would be
// invalid HTML and double-fire both click handlers. The clickable version
// (with the who/when/note popover) belongs in the expanded detail panel instead.
const AdjustmentBadge = ({ correctionMeta, interactive = true }) => {
    const [open, setOpen] = useState(false);
    if (!correctionMeta) return null;

    if (!interactive) {
        return (
            <span className="adjustment-badge" title="Adjusted from a prior correction — see details below">
                <History size={12} /> Adjusted from a prior correction
            </span>
        );
    }

    return (
        <span className="adjustment-badge-wrap">
            <button type="button" className="adjustment-badge" onClick={() => setOpen((v) => !v)}>
                <History size={12} /> Adjusted from a prior correction
            </button>
            {open && (
                <div className="adjustment-popover">
                    <p><strong>Original system verdict:</strong> {correctionMeta.system_output}</p>
                    <p><strong>Flagged:</strong> {correctionMeta.flagged_at ? new Date(correctionMeta.flagged_at).toLocaleString() : 'unknown'}</p>
                    {correctionMeta.note && <p><strong>Note:</strong> {correctionMeta.note}</p>}
                </div>
            )}
        </span>
    );
};

export default AdjustmentBadge;
