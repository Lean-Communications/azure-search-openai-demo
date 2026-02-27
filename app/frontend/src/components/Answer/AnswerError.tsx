import { AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";

import styles from "./Answer.module.css";

interface Props {
    error: string;
    onRetry: () => void;
}

export const AnswerError = ({ error, onRetry }: Props) => {
    return (
        <div className={styles.answerContainer}>
            <div className="flex gap-3">
                <div className="shrink-0 pt-0.5">
                    <AlertCircle className="h-7 w-7 text-red-500" aria-hidden="true" aria-label="Error icon" />
                </div>
                <div className="flex-1">
                    <p className={styles.answerText}>{error}</p>
                    <Button className={styles.retryButton} onClick={onRetry}>
                        Retry
                    </Button>
                </div>
            </div>
        </div>
    );
};
