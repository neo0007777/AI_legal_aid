import { useState, useEffect, useCallback } from 'react';
import { ShieldCheck, Check, X, Loader2, ArrowUpCircle, ArrowDownCircle } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import './AdminCorrections.css';

// Harness-sprint Part A: "your demo asset -- it has to look good, not just work."
// Two sections: the pending_review queue (needs a decision) on top, and the
// full log (both directions, all statuses) below it.
const AdminCorrections = () => {
    const { token } = useAuth();
    const [corrections, setCorrections] = useState(null);
    const [error, setError] = useState(null);
    const [actingOn, setActingOn] = useState(null);

    const load = useCallback(async () => {
        setError(null);
        try {
            const res = await fetch('/api/admin/corrections', { headers: { Authorization: `Bearer ${token}` } });
            if (!res.ok) {
                if (res.status === 403) throw new Error("You don't have admin access, so this list can't be loaded.");
                throw new Error(`Failed to load corrections (${res.status})`);
            }
            const data = await res.json();
            setCorrections(data.corrections);
        } catch (err) {
            setError(err.message);
        }
    }, [token]);

    useEffect(() => { load(); }, [load]);

    const act = async (id, action) => {
        setActingOn(id);
        try {
            const res = await fetch(`/api/admin/corrections/${id}/${action}`, {
                method: 'POST',
                headers: { Authorization: `Bearer ${token}` },
            });
            if (!res.ok) throw new Error(`Failed to ${action} (${res.status})`);
            await load();
        } catch (err) {
            setError(err.message);
        } finally {
            setActingOn(null);
        }
    };

    if (error && !corrections) {
        return (
            <div className="admin-corrections-wrapper animate-fade-in">
                <div className="verify-error-banner"><X size={16} /> {error}</div>
            </div>
        );
    }

    if (!corrections) {
        return (
            <div className="admin-corrections-wrapper animate-fade-in">
                <div className="verify-progress-state"><Loader2 size={28} className="spin" /><p>Loading corrections…</p></div>
            </div>
        );
    }

    const pending = corrections.filter((c) => c.status === 'pending_review').sort((a, b) => new Date(b.flagged_at) - new Date(a.flagged_at));
    const all = [...corrections].sort((a, b) => new Date(b.flagged_at) - new Date(a.flagged_at));

    return (
        <div className="admin-corrections-wrapper animate-fade-in">
            <div className="admin-header">
                <div className="badge-chip"><ShieldCheck size={16} /><span>Admin</span></div>
                <h2>Correction Memory</h2>
                <p className="subtitle">
                    Loosen corrections (toward Verified) wait here until confirmed. Tighten corrections
                    (toward Mismatch / Not found) already took effect the moment they were flagged.
                </p>
            </div>

            {error && <div className="verify-error-banner"><X size={16} /> {error}</div>}

            <section className="admin-section">
                <h3>Pending review ({pending.length})</h3>
                {pending.length === 0 ? (
                    <p className="admin-empty">Nothing waiting on a decision.</p>
                ) : (
                    <div className="correction-list">
                        {pending.map((c) => (
                            <div key={c.id} className="correction-row pending">
                                <CorrectionSummary c={c} />
                                <div className="correction-actions">
                                    <button className="outline btn-sm" disabled={actingOn === c.id} onClick={() => act(c.id, 'reject')}>
                                        <X size={14} /> Reject
                                    </button>
                                    <button className="btn-sm" disabled={actingOn === c.id} onClick={() => act(c.id, 'confirm')}>
                                        {actingOn === c.id ? <Loader2 size={14} className="spin" /> : <Check size={14} />} Confirm
                                    </button>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </section>

            <section className="admin-section">
                <h3>Full correction log ({all.length})</h3>
                {all.length === 0 ? (
                    <p className="admin-empty">No corrections have been flagged yet.</p>
                ) : (
                    <div className="correction-list">
                        {all.map((c) => <div key={c.id} className="correction-row"><CorrectionSummary c={c} showStatus /></div>)}
                    </div>
                )}
            </section>
        </div>
    );
};

const CorrectionSummary = ({ c, showStatus }) => (
    <div className="correction-summary">
        <div className="correction-top-line">
            {c.direction === 'tighten'
                ? <span className="direction-tag tighten"><ArrowDownCircle size={13} /> tighten</span>
                : <span className="direction-tag loosen"><ArrowUpCircle size={13} /> loosen</span>}
            <span className="correction-verdicts">{c.system_output} <strong>&rarr;</strong> {c.correct_output}</span>
            {showStatus && <span className={`status-tag ${c.status}`}>{c.status.replace('_', ' ')}</span>}
        </div>
        <div className="correction-meta-line">
            {c.trigger_type} · flagged {c.flagged_at ? new Date(c.flagged_at).toLocaleString() : 'unknown'}
            {c.reviewed_at && ` · reviewed ${new Date(c.reviewed_at).toLocaleString()}`}
        </div>
        {c.note && <div className="correction-note">"{c.note}"</div>}
        <div className="correction-signature">{c.input_signature}</div>
    </div>
);

export default AdminCorrections;
