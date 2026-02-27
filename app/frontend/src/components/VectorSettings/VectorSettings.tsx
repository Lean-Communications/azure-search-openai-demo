import { useEffect, useState, useId } from "react";
import { useTranslation } from "react-i18next";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

import styles from "./VectorSettings.module.css";
import { HelpCallout } from "../../components/HelpCallout";
import { RetrievalMode } from "../../api";

interface Props {
    showImageOptions?: boolean;
    defaultRetrievalMode: RetrievalMode;
    defaultSearchTextEmbeddings?: boolean;
    defaultSearchImageEmbeddings?: boolean;
    updateRetrievalMode: (retrievalMode: RetrievalMode) => void;
    updateSearchTextEmbeddings: (searchTextEmbeddings: boolean) => void;
    updateSearchImageEmbeddings: (searchImageEmbeddings: boolean) => void;
}

const retrievalModeMap: Record<string, RetrievalMode> = {
    hybrid: RetrievalMode.Hybrid,
    vectors: RetrievalMode.Vectors,
    text: RetrievalMode.Text
};

export const VectorSettings = ({
    updateRetrievalMode,
    updateSearchTextEmbeddings,
    updateSearchImageEmbeddings,
    showImageOptions,
    defaultRetrievalMode,
    defaultSearchTextEmbeddings = true,
    defaultSearchImageEmbeddings = true
}: Props) => {
    const [retrievalMode, setRetrievalMode] = useState<RetrievalMode>(defaultRetrievalMode || RetrievalMode.Hybrid);
    const [searchTextEmbeddings, setSearchTextEmbeddings] = useState<boolean>(defaultSearchTextEmbeddings);
    const [searchImageEmbeddings, setSearchImageEmbeddings] = useState<boolean>(defaultSearchImageEmbeddings);

    const onRetrievalModeChange = (value: string) => {
        const mode = retrievalModeMap[value] || RetrievalMode.Hybrid;
        setRetrievalMode(mode);
        updateRetrievalMode(mode);
    };

    const onSearchTextEmbeddingsChange = (checked: boolean | "indeterminate") => {
        const val = checked === true;
        setSearchTextEmbeddings(val);
        updateSearchTextEmbeddings(val);
    };

    const onSearchImageEmbeddingsChange = (checked: boolean | "indeterminate") => {
        const val = checked === true;
        setSearchImageEmbeddings(val);
        updateSearchImageEmbeddings(val);
    };

    useEffect(() => {
        if (!showImageOptions) {
            setSearchImageEmbeddings(false);
            updateSearchImageEmbeddings(false);
        } else {
            setSearchImageEmbeddings(defaultSearchImageEmbeddings);
            updateSearchImageEmbeddings(defaultSearchImageEmbeddings);
        }
    }, [showImageOptions, updateSearchImageEmbeddings, defaultSearchImageEmbeddings]);

    const retrievalModeId = useId();
    const retrievalModeFieldId = useId();
    const vectorFieldsId = useId();
    const vectorFieldsFieldId = useId();
    const { t } = useTranslation();

    const retrievalModeKey = Object.entries(retrievalModeMap).find(([, v]) => v === retrievalMode)?.[0] || "hybrid";

    return (
        <div className={`${styles.container} flex flex-col gap-2.5`}>
            <div>
                <HelpCallout
                    labelId={retrievalModeId}
                    fieldId={retrievalModeFieldId}
                    helpText={t("helpTexts.retrievalMode")}
                    label={t("labels.retrievalMode.label")}
                />
                <Select value={retrievalModeKey} onValueChange={onRetrievalModeChange}>
                    <SelectTrigger id={retrievalModeFieldId} className="mt-1">
                        <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="hybrid">{t("labels.retrievalMode.options.hybrid")}</SelectItem>
                        <SelectItem value="vectors">{t("labels.retrievalMode.options.vectors")}</SelectItem>
                        <SelectItem value="text">{t("labels.retrievalMode.options.texts")}</SelectItem>
                    </SelectContent>
                </Select>
            </div>

            {showImageOptions && [RetrievalMode.Vectors, RetrievalMode.Hybrid].includes(retrievalMode) && (
                <fieldset className={styles.fieldset}>
                    <legend className={styles.legend}>{t("labels.vector.label")}</legend>
                    <div className="flex flex-col gap-2">
                        <div>
                            <HelpCallout
                                labelId={vectorFieldsId + "-text"}
                                fieldId={vectorFieldsFieldId + "-text"}
                                helpText={t("helpTexts.textEmbeddings")}
                                label={t("labels.vector.options.embedding")}
                            />
                            <div className="flex items-center gap-2 mt-1">
                                <Checkbox
                                    id={vectorFieldsFieldId + "-text"}
                                    checked={searchTextEmbeddings}
                                    onCheckedChange={onSearchTextEmbeddingsChange}
                                />
                            </div>
                        </div>
                        <div>
                            <HelpCallout
                                labelId={vectorFieldsId + "-image"}
                                fieldId={vectorFieldsFieldId + "-image"}
                                helpText={t("helpTexts.imageEmbeddings")}
                                label={t("labels.vector.options.imageEmbedding")}
                            />
                            <div className="flex items-center gap-2 mt-1">
                                <Checkbox
                                    id={vectorFieldsFieldId + "-image"}
                                    checked={searchImageEmbeddings}
                                    onCheckedChange={onSearchImageEmbeddingsChange}
                                />
                            </div>
                        </div>
                    </div>
                </fieldset>
            )}
        </div>
    );
};
