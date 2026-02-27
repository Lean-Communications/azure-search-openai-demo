import { useState, useEffect, useContext } from "react";
import { ArrowUp, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useTranslation } from "react-i18next";

import styles from "./QuestionInput.module.css";
import { SpeechInput } from "./SpeechInput";
import { LoginContext } from "../../loginContext";
import { requireLogin } from "../../authConfig";

interface Props {
    onSend: (question: string) => void;
    disabled: boolean;
    initQuestion?: string;
    placeholder?: string;
    clearOnSend?: boolean;
    showSpeechInput?: boolean;
    onStop: () => void;
    isStreaming: boolean;
    isLoading: boolean;
}

export const QuestionInput = ({ onSend, onStop, disabled, placeholder, clearOnSend, initQuestion, showSpeechInput, isStreaming, isLoading }: Props) => {
    const [question, setQuestion] = useState<string>("");
    const { loggedIn } = useContext(LoginContext);
    const { t } = useTranslation();
    const [isComposing, setIsComposing] = useState(false);

    useEffect(() => {
        initQuestion && setQuestion(initQuestion);
    }, [initQuestion]);

    const sendQuestion = () => {
        if (disabled || !question.trim()) {
            return;
        }

        onSend(question);

        if (clearOnSend) {
            setQuestion("");
        }
    };

    const onEnterPress = (ev: React.KeyboardEvent<Element>) => {
        if (isComposing) return;

        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            sendQuestion();
        }
    };

    const handleCompositionStart = () => {
        setIsComposing(true);
    };
    const handleCompositionEnd = () => {
        setIsComposing(false);
    };

    const onQuestionChange = (ev: React.ChangeEvent<HTMLTextAreaElement>) => {
        setQuestion(ev.target.value || "");
    };

    const disableRequiredAccessControl = requireLogin && !loggedIn;
    const sendQuestionDisabled = disabled || !question.trim() || disableRequiredAccessControl;

    if (disableRequiredAccessControl) {
        placeholder = "Please login to continue...";
    }

    return (
        <div className={`${styles.questionInputContainer} flex`}>
            <Textarea
                className={`${styles.questionInputTextArea} min-h-0 border-0 resize-none bg-transparent focus-visible:ring-0 focus-visible:ring-offset-0 rounded-none`}
                disabled={disableRequiredAccessControl}
                placeholder={placeholder}
                value={question}
                onChange={onQuestionChange}
                onKeyDown={onEnterPress}
                onCompositionStart={handleCompositionStart}
                onCompositionEnd={handleCompositionEnd}
                rows={1}
            />
            <div className={styles.questionInputButtonsContainer}>
                {isStreaming || isLoading ? (
                    <Tooltip>
                        <TooltipTrigger asChild>
                            <button className={styles.sendButton} onClick={onStop} aria-label={t("tooltips.stopStreaming")}>
                                <Square className="h-4 w-4" fill="white" stroke="white" />
                            </button>
                        </TooltipTrigger>
                        <TooltipContent>{t("tooltips.stopStreaming")}</TooltipContent>
                    </Tooltip>
                ) : (
                    <Tooltip>
                        <TooltipTrigger asChild>
                            <button
                                className={`${styles.sendButton} ${sendQuestionDisabled ? styles.sendButtonDisabled : ""}`}
                                disabled={sendQuestionDisabled}
                                onClick={sendQuestion}
                                aria-label={t("tooltips.submitQuestion")}
                            >
                                <ArrowUp className="h-4.5 w-4.5" strokeWidth={2.5} />
                            </button>
                        </TooltipTrigger>
                        <TooltipContent>{t("tooltips.submitQuestion")}</TooltipContent>
                    </Tooltip>
                )}
            </div>
            {showSpeechInput && <SpeechInput updateQuestion={setQuestion} />}
        </div>
    );
};
