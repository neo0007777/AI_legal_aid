import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Languages, Loader2, AlertTriangle, Undo2 } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useLanguage } from '../context/LanguageContext';
import './TranslateAction.css';

// Shared "Translate to {language}" action embedded in every feature's result
// view (Legal Aid, Draft Assistant, Draft Review, Contract Analysis, ...).
// One component, one backend call (POST /translate) -- no per-feature
// translation function, per the app-wide language switcher design.
//
// Correctness contract this component depends on and must never violate:
// translation is a RENDERING step over already-verified English text. It
// never re-triggers generation/verification -- `text`/`citations` are always
// the already-displayed English result, passed in as-is. The disclaimer is
// mandatory and not dismissible; the original English stays one click away.
const TranslateAction = ({ sourceType, text, citations = [] }) => {
    const { t } = useTranslation();
    const { getAuthHeaders } = useAuth();
    const { languageCode, currentLanguage } = useLanguage();

    const [translation, setTranslation] = useState(null); // { translated_text, disclaimer, target_lang }
    const [isTranslating, setIsTranslating] = useState(false);
    const [error, setError] = useState('');
    const [showingOriginal, setShowingOriginal] = useState(false);
    const [translatedForLang, setTranslatedForLang] = useState(null);

    // Nothing to translate into -- app language is already English.
    if (languageCode === 'en' || !text) return null;

    const handleTranslate = async () => {
        setIsTranslating(true);
        setError('');
        try {
            const res = await fetch('/api/translate', {
                method: 'POST',
                headers: getAuthHeaders(),
                body: JSON.stringify({
                    source_type: sourceType,
                    target_lang: languageCode,
                    text,
                    citations,
                }),
            });
            if (!res.ok) {
                let msg = t('translate.error');
                try { const e = await res.json(); msg = e.detail || msg; } catch { /* ignore */ }
                throw new Error(msg);
            }
            const data = await res.json();
            setTranslation(data);
            setTranslatedForLang(languageCode);
            setShowingOriginal(false);
        } catch (err) {
            setError(err.message || t('translate.error'));
        } finally {
            setIsTranslating(false);
        }
    };

    const staleTranslation = translation && translatedForLang !== languageCode;

    return (
        <div className="translate-action-block">
            {!translation || staleTranslation ? (
                <button
                    type="button"
                    className="translate-action-btn"
                    onClick={handleTranslate}
                    disabled={isTranslating}
                >
                    {isTranslating ? (
                        <><Loader2 size={14} className="spin" /> {t('translate.translating')}</>
                    ) : (
                        <><Languages size={14} /> {t('translate.button', { language: currentLanguage.nativeLabel })}</>
                    )}
                </button>
            ) : (
                <div className="translate-result-card">
                    <div className="translate-disclaimer">
                        <AlertTriangle size={13} />
                        <span>{translation.disclaimer || t('translate.disclaimer')}</span>
                    </div>

                    <div className="translate-toggle-row">
                        <button
                            type="button"
                            className={`translate-toggle-btn ${!showingOriginal ? 'active' : ''}`}
                            onClick={() => setShowingOriginal(false)}
                        >
                            {t('translate.viewTranslated')}
                        </button>
                        <button
                            type="button"
                            className={`translate-toggle-btn ${showingOriginal ? 'active' : ''}`}
                            onClick={() => setShowingOriginal(true)}
                        >
                            <Undo2 size={12} /> {t('translate.viewOriginal')}
                        </button>
                    </div>

                    <div className="translate-text-body">
                        {showingOriginal ? text : translation.translated_text}
                    </div>
                </div>
            )}

            {error && (
                <div className="translate-error-note">
                    <AlertTriangle size={13} /> {error}
                </div>
            )}
        </div>
    );
};

export default TranslateAction;
