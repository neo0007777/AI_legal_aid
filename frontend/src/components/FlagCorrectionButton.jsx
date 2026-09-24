import { useState } from 'react';
import { Flag, Loader2, CheckCircle2, Clock } from 'lucide-react';
import './FlagCorrectionButton.css';

const STATES = ['Verified', 'Mismatch', 'Not found in indexed corpus'];

// Harness-sprint Part A: "Flag this result" on the citation trail and the
// contradiction diff view. The feedback after submit is the whole point --
// a tighten flag and a loosen flag are NOT the same thing, and the person
// flagging has to see that distinction immediately, not just trust the backend.
const FlagCorrectionButton = ({ reportId, citationIndex, currentStatus, token, onFlagged }) => {
    const [open, setOpen] = useState(false);
    const [correctOutput, setCorrectOutput] = useState(STATES.find((s) => s !== currentStatus) || STATES[0]);
    const [note, setNote] = useState('');
    const [submitting, setSubmitting] = useState(false);
    const [feedback, setFeedback] = useState(null);
    const [error, setError] = useState(null);

    const submit = async () => {
        setSubmitting(true);
        setError(null);
        try {
            const res = await fetch(`/api/citations/${reportId}:${citationIndex}/flag-correction`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
                body: JSON.stringify({ correct_output: correctOutput, note: note || undefined }),
            });
            if (!res.ok) {
                const e = await res.json().catch(() => ({}));
                throw new Error(e.detail || 'Failed to flag this result.');
            }
            const data = await res.json();
            setFeedback(data);
            setOpen(false);
            if (onFlagged) onFlagged(citationIndex, { ...data, correct_output: correctOutput });
        } catch (err) {
            setError(err.message);
        } finally {
            setSubmitting(false);
        }
    };

    if (feedback) {
        return (
            <div className={`flag-feedback ${feedback.direction}`}>
                {feedback.direction === 'tighten' ? <CheckCircle2 size={14} /> : <Clock size={14} />}
                {feedback.message}
            </div>
        );
    }

    if (!open) {
        return (
            <button className="outline btn-sm flag-correction-trigger" onClick={() => setOpen(true)}>
                <Flag size={14} /> Flag this result
            </button>
        );
    }

    return (
        <div className="flag-correction-form">
            <label>This should actually be:</label>
            <select value={correctOutput} onChange={(e) => setCorrectOutput(e.target.value)}>
                {STATES.filter((s) => s !== currentStatus).map((s) => (
                    <option key={s} value={s}>{s}</option>
                ))}
            </select>
            <textarea placeholder="Optional note" value={note} onChange={(e) => setNote(e.target.value)} rows={2} />
            {error && <p className="flag-error">{error}</p>}
            <div className="flag-form-actions">
                <button className="outline btn-sm" onClick={() => setOpen(false)} disabled={submitting}>Cancel</button>
                <button className="btn-sm" onClick={submit} disabled={submitting}>
                    {submitting && <Loader2 size={14} className="spin" />} Submit
                </button>
            </div>
        </div>
    );
};

export default FlagCorrectionButton;
