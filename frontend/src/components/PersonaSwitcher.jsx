import { usePersona, PERSONAS } from '../context/PersonaContext';
import './PersonaSwitcher.css';

// S3 Task 1: one flow, persona-aware framing at the moments it changes what
// someone needs -- not four separate UIs. Switching persona never hides
// anything from the others, it only changes default view/copy emphasis.
const PersonaSwitcher = () => {
    const { personaId, setPersonaId } = usePersona();

    return (
        <div className="persona-switcher" role="tablist" aria-label="Who are you using this as?">
            {Object.values(PERSONAS).map((p) => (
                <button
                    key={p.id}
                    type="button"
                    role="tab"
                    aria-selected={personaId === p.id}
                    className={`persona-pill ${personaId === p.id ? 'active' : ''}`}
                    onClick={() => setPersonaId(p.id)}
                >
                    <p.icon size={15} /> {p.label}
                </button>
            ))}
        </div>
    );
};

export default PersonaSwitcher;
