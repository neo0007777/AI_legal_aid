import { useState, useRef, useEffect } from 'react';
import { Mic, MicOff } from 'lucide-react';
import './VoiceInputButton.css';

// Harness-sprint Part D: browser-native Web Speech API only -- no backend call,
// no new dependency. Populates the field for the user to review/edit; never
// submits anything on its own. If the browser doesn't support it (Web Speech
// API is not implemented in WebKit/Safari), the button doesn't render at all
// rather than showing something that would error on click.
const VoiceInputButton = ({ onTranscript, disabled }) => {
    const [listening, setListening] = useState(false);
    const [supported, setSupported] = useState(false);
    const recognitionRef = useRef(null);

    useEffect(() => {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        setSupported(!!SpeechRecognition);
        if (!SpeechRecognition) return;

        const recognition = new SpeechRecognition();
        recognition.continuous = false;
        recognition.interimResults = false;
        recognition.lang = 'en-IN';

        recognition.onresult = (event) => {
            const transcript = Array.from(event.results).map((r) => r[0].transcript).join(' ');
            onTranscript(transcript);
        };
        recognition.onerror = () => setListening(false);
        recognition.onend = () => setListening(false);

        recognitionRef.current = recognition;
        return () => recognition.stop();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    if (!supported) return null;

    const toggle = () => {
        if (listening) {
            recognitionRef.current.stop();
            setListening(false);
        } else {
            recognitionRef.current.start();
            setListening(true);
        }
    };

    return (
        <button
            type="button"
            className={`voice-input-btn ${listening ? 'listening' : ''}`}
            onClick={toggle}
            disabled={disabled}
            title={listening ? 'Stop dictation' : 'Dictate this field'}
        >
            {listening ? <MicOff size={15} /> : <Mic size={15} />}
            {listening && <span className="voice-pulse" />}
        </button>
    );
};

export default VoiceInputButton;
