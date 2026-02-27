import { useId } from "react";
import { useTranslation } from "react-i18next";
import { Languages } from "lucide-react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

import { supportedLngs } from "./config";
import styles from "./LanguagePicker.module.css";

interface Props {
    onLanguageChange: (language: string) => void;
}

export const LanguagePicker = ({ onLanguageChange }: Props) => {
    const { i18n, t } = useTranslation();
    const languagePickerId = useId();

    return (
        <div className={styles.languagePicker}>
            <Languages className={`${styles.languagePickerIcon} h-6 w-6`} />
            <Select value={i18n.language} onValueChange={onLanguageChange}>
                <SelectTrigger id={languagePickerId} aria-label={t("labels.languagePicker")}>
                    <SelectValue />
                </SelectTrigger>
                <SelectContent>
                    {Object.entries(supportedLngs).map(([code, details]) => (
                        <SelectItem key={code} value={code}>
                            {details.name}
                        </SelectItem>
                    ))}
                </SelectContent>
            </Select>
        </div>
    );
};
