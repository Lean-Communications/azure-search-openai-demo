import { History } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useTranslation } from "react-i18next";

import styles from "./HistoryButton.module.css";

interface Props {
    className?: string;
    onClick: () => void;
    disabled?: boolean;
}

export const HistoryButton = ({ className, disabled, onClick }: Props) => {
    const { t } = useTranslation();
    return (
        <div className={`${styles.container} ${className ?? ""}`}>
            <Button variant="outline" disabled={disabled} onClick={onClick}>
                <History className="h-5 w-5" />
                {t("history.openChatHistory")}
            </Button>
        </div>
    );
};
