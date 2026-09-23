import React, { createContext, useContext, useState, useEffect } from 'react';
import { Gavel, GraduationCap, Landmark, ClipboardList } from 'lucide-react';

const PersonaContext = createContext();
export const usePersona = () => useContext(PersonaContext);

// S3 Task 1: one flow, persona-aware framing -- not four separate UIs. Each
// entry only changes copy/emphasis/default-view, never what's visible to
// other personas (per the brief: no persona should hide info from another).
export const PERSONAS = {
    lawyer: {
        id: 'lawyer',
        label: 'Lawyer',
        icon: Gavel,
        tagline: 'Verify a filing before it goes to court.',
        defaultView: 'list',
        emphasizeExport: true,
    },
    paralegal: {
        id: 'paralegal',
        label: 'Paralegal',
        icon: ClipboardList,
        tagline: 'High-volume citation audit, ready to hand to a supervising lawyer.',
        defaultView: 'list',
        emphasizeExport: true,
    },
    student: {
        id: 'student',
        label: 'Law Student',
        icon: GraduationCap,
        tagline: 'Learn why a citation is grounded — or isn’t — one step at a time.',
        defaultView: 'walkthrough',
        emphasizeExport: false,
    },
    judge: {
        id: 'judge',
        label: 'Judge',
        icon: Landmark,
        tagline: 'The layer that would have caught it.',
        defaultView: 'list',
        emphasizeExport: false,
    },
};

export const PersonaProvider = ({ children }) => {
    const [personaId, setPersonaId] = useState(() => {
        try {
            return localStorage.getItem('lexsetu_persona') || 'lawyer';
        } catch {
            return 'lawyer';
        }
    });

    useEffect(() => {
        try {
            localStorage.setItem('lexsetu_persona', personaId);
        } catch { /* ignore */ }
    }, [personaId]);

    const persona = PERSONAS[personaId] || PERSONAS.lawyer;

    return (
        <PersonaContext.Provider value={{ personaId, setPersonaId, persona, personas: PERSONAS }}>
            {children}
        </PersonaContext.Provider>
    );
};
