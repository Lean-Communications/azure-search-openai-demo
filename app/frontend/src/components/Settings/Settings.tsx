import { useId } from "react";
import { useTranslation } from "react-i18next";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { HelpCallout } from "../HelpCallout";
import { VectorSettings } from "../VectorSettings";
import { RetrievalMode } from "../../api";
import styles from "./Settings.module.css";

export interface SettingsProps {
    promptTemplate: string;
    temperature: number;
    retrieveCount: number;
    agenticReasoningEffort: string;
    seed: number | null;
    minimumSearchScore: number;
    minimumRerankerScore: number;
    useSemanticRanker: boolean;
    useSemanticCaptions: boolean;
    useQueryRewriting: boolean;
    reasoningEffort: string;
    excludeCategory: string;
    includeCategory: string;
    retrievalMode: RetrievalMode;
    sendTextSources: boolean;
    sendImageSources: boolean;
    searchTextEmbeddings: boolean;
    searchImageEmbeddings: boolean;
    showSemanticRankerOption: boolean;
    showQueryRewritingOption: boolean;
    showReasoningEffortOption: boolean;
    showMultimodalOptions: boolean;
    showVectorOption: boolean;
    useLogin: boolean;
    loggedIn: boolean;
    requireAccessControl: boolean;
    className?: string;
    onChange: (field: string, value: any) => void;
    streamingEnabled?: boolean;
    shouldStream?: boolean;
    useSuggestFollowupQuestions?: boolean;
    promptTemplatePrefix?: string;
    promptTemplateSuffix?: string;
    showAgenticRetrievalOption?: boolean;
    useAgenticKnowledgeBase?: boolean;
    hideMinimalRetrievalReasoningOption?: boolean;
    useWebSource?: boolean;
    showWebSourceOption?: boolean;
    useSharePointSource?: boolean;
    showSharePointSourceOption?: boolean;
}

export const Settings = ({
    promptTemplate,
    temperature,
    retrieveCount,
    agenticReasoningEffort,
    seed,
    minimumSearchScore,
    minimumRerankerScore,
    useSemanticRanker,
    useSemanticCaptions,
    useQueryRewriting,
    reasoningEffort,
    excludeCategory,
    includeCategory,
    retrievalMode,
    searchTextEmbeddings,
    searchImageEmbeddings,
    sendTextSources,
    sendImageSources,
    showSemanticRankerOption,
    showQueryRewritingOption,
    showReasoningEffortOption,
    showMultimodalOptions,
    showVectorOption,
    useLogin,
    loggedIn,
    requireAccessControl,
    className,
    onChange,
    streamingEnabled,
    shouldStream,
    useSuggestFollowupQuestions,
    promptTemplatePrefix,
    promptTemplateSuffix,
    showAgenticRetrievalOption,
    useAgenticKnowledgeBase = false,
    hideMinimalRetrievalReasoningOption = false,
    useWebSource = false,
    showWebSourceOption = false,
    useSharePointSource = false,
    showSharePointSourceOption = false
}: SettingsProps) => {
    const { t } = useTranslation();

    // Form field IDs
    const promptTemplateId = useId();
    const promptTemplateFieldId = useId();
    const temperatureId = useId();
    const temperatureFieldId = useId();
    const seedId = useId();
    const seedFieldId = useId();
    const agenticRetrievalId = useId();
    const agenticRetrievalFieldId = useId();
    const webSourceId = useId();
    const webSourceFieldId = useId();
    const sharePointSourceId = useId();
    const sharePointSourceFieldId = useId();
    const searchScoreId = useId();
    const searchScoreFieldId = useId();
    const rerankerScoreId = useId();
    const rerankerScoreFieldId = useId();
    const retrieveCountId = useId();
    const retrieveCountFieldId = useId();
    const agenticReasoningEffortId = useId();
    const agenticReasoningEffortFieldId = useId();
    const includeCategoryId = useId();
    const includeCategoryFieldId = useId();
    const excludeCategoryId = useId();
    const excludeCategoryFieldId = useId();
    const semanticRankerId = useId();
    const semanticRankerFieldId = useId();
    const queryRewritingFieldId = useId();
    const reasoningEffortFieldId = useId();
    const semanticCaptionsId = useId();
    const semanticCaptionsFieldId = useId();
    const shouldStreamId = useId();
    const shouldStreamFieldId = useId();
    const suggestFollowupQuestionsId = useId();
    const suggestFollowupQuestionsFieldId = useId();

    const webSourceDisablesStreamingAndFollowup = !!useWebSource;

    return (
        <div className={className}>
            {streamingEnabled && (
                <>
                    <div className={styles.settingsSeparator}>
                        <HelpCallout
                            labelId={shouldStreamId}
                            fieldId={shouldStreamFieldId}
                            helpText={t("helpTexts.streamChat")}
                            label={t("labels.shouldStream")}
                        />
                        <div className="flex items-center gap-2 mt-1">
                            <Checkbox
                                id={shouldStreamFieldId}
                                checked={webSourceDisablesStreamingAndFollowup ? false : shouldStream}
                                onCheckedChange={checked => onChange("shouldStream", !!checked)}
                                disabled={webSourceDisablesStreamingAndFollowup}
                            />
                        </div>
                    </div>

                    <div className={styles.settingsSeparator}>
                        <HelpCallout
                            labelId={suggestFollowupQuestionsId}
                            fieldId={suggestFollowupQuestionsFieldId}
                            helpText={t("helpTexts.suggestFollowupQuestions")}
                            label={t("labels.useSuggestFollowupQuestions")}
                        />
                        <div className="flex items-center gap-2 mt-1">
                            <Checkbox
                                id={suggestFollowupQuestionsFieldId}
                                checked={webSourceDisablesStreamingAndFollowup ? false : useSuggestFollowupQuestions}
                                onCheckedChange={checked => onChange("useSuggestFollowupQuestions", !!checked)}
                                disabled={webSourceDisablesStreamingAndFollowup}
                            />
                        </div>
                    </div>
                </>
            )}

            <h3 className={styles.sectionHeader}>{t("searchSettings")}</h3>

            {showAgenticRetrievalOption && (
                <div className={styles.settingsSeparator}>
                    <HelpCallout
                        labelId={agenticRetrievalId}
                        fieldId={agenticRetrievalFieldId}
                        helpText={t("helpTexts.useAgenticKnowledgeBase")}
                        label={t("labels.useAgenticKnowledgeBase")}
                    />
                    <div className="flex items-center gap-2 mt-1">
                        <Checkbox
                            id={agenticRetrievalFieldId}
                            checked={useAgenticKnowledgeBase}
                            onCheckedChange={checked => onChange("useAgenticKnowledgeBase", !!checked)}
                        />
                    </div>
                </div>
            )}

            {showAgenticRetrievalOption && useAgenticKnowledgeBase && (
                <div className={styles.settingsSeparator}>
                    <HelpCallout
                        labelId={agenticReasoningEffortId}
                        fieldId={agenticReasoningEffortFieldId}
                        helpText={t("helpTexts.agenticReasoningEffort")}
                        label={t("labels.agenticReasoningEffort")}
                    />
                    <Select
                        value={agenticReasoningEffort}
                        onValueChange={value => {
                            onChange("agenticReasoningEffort", value);
                            if (value === "minimal" && useWebSource) {
                                onChange("useWebSource", false);
                            }
                        }}
                    >
                        <SelectTrigger id={agenticReasoningEffortFieldId} className="mt-1">
                            <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="minimal">{t("labels.agenticReasoningEffortOptions.minimal")}</SelectItem>
                            <SelectItem value="low">{t("labels.agenticReasoningEffortOptions.low")}</SelectItem>
                            <SelectItem value="medium">{t("labels.agenticReasoningEffortOptions.medium")}</SelectItem>
                        </SelectContent>
                    </Select>
                </div>
            )}

            {showAgenticRetrievalOption && useAgenticKnowledgeBase && showWebSourceOption && (
                <div className={styles.settingsSeparator}>
                    <HelpCallout
                        labelId={webSourceId}
                        fieldId={webSourceFieldId}
                        helpText={t("helpTexts.useWebSource")}
                        label={t("labels.useWebSource")}
                    />
                    <div className="flex items-center gap-2 mt-1">
                        <Checkbox
                            id={webSourceFieldId}
                            checked={useWebSource}
                            onCheckedChange={checked => {
                                onChange("useWebSource", !!checked);
                                if (checked) {
                                    if (shouldStream) onChange("shouldStream", false);
                                    if (useSuggestFollowupQuestions) onChange("useSuggestFollowupQuestions", false);
                                }
                            }}
                            disabled={!useAgenticKnowledgeBase || agenticReasoningEffort === "minimal"}
                        />
                    </div>
                </div>
            )}

            {showAgenticRetrievalOption && useAgenticKnowledgeBase && showSharePointSourceOption && (
                <div className={styles.settingsSeparator}>
                    <HelpCallout
                        labelId={sharePointSourceId}
                        fieldId={sharePointSourceFieldId}
                        helpText={t("helpTexts.useSharePointSource")}
                        label={t("labels.useSharePointSource")}
                    />
                    <div className="flex items-center gap-2 mt-1">
                        <Checkbox
                            id={sharePointSourceFieldId}
                            checked={useSharePointSource}
                            onCheckedChange={checked => onChange("useSharePointSource", !!checked)}
                            disabled={!useAgenticKnowledgeBase}
                        />
                    </div>
                </div>
            )}

            {!useAgenticKnowledgeBase && (
                <div className={styles.settingsSeparator}>
                    <HelpCallout
                        labelId={searchScoreId}
                        fieldId={searchScoreFieldId}
                        helpText={t("helpTexts.searchScore")}
                        label={t("labels.minimumSearchScore")}
                    />
                    <Input
                        id={searchScoreFieldId}
                        className="mt-1"
                        type="number"
                        min={0}
                        step={0.01}
                        defaultValue={minimumSearchScore.toString()}
                        onChange={e => onChange("minimumSearchScore", parseFloat(e.target.value || "0"))}
                    />
                </div>
            )}

            {showSemanticRankerOption && (
                <div className={styles.settingsSeparator}>
                    <HelpCallout
                        labelId={rerankerScoreId}
                        fieldId={rerankerScoreFieldId}
                        helpText={t("helpTexts.rerankerScore")}
                        label={t("labels.minimumRerankerScore")}
                    />
                    <Input
                        id={rerankerScoreFieldId}
                        className="mt-1"
                        type="number"
                        min={1}
                        max={4}
                        step={0.1}
                        defaultValue={minimumRerankerScore.toString()}
                        onChange={e => onChange("minimumRerankerScore", parseFloat(e.target.value || "0"))}
                    />
                </div>
            )}

            {!useAgenticKnowledgeBase && (
                <div className={styles.settingsSeparator}>
                    <HelpCallout
                        labelId={retrieveCountId}
                        fieldId={retrieveCountFieldId}
                        helpText={t("helpTexts.retrieveNumber")}
                        label={t("labels.retrieveCount")}
                    />
                    <Input
                        id={retrieveCountFieldId}
                        className="mt-1"
                        type="number"
                        min={1}
                        max={50}
                        defaultValue={retrieveCount.toString()}
                        onChange={e => onChange("retrieveCount", parseInt(e.target.value || "3"))}
                    />
                </div>
            )}

            <div className={styles.settingsSeparator}>
                <HelpCallout
                    labelId={includeCategoryId}
                    fieldId={includeCategoryFieldId}
                    helpText={t("helpTexts.includeCategory")}
                    label={t("labels.includeCategory")}
                />
                <Select value={includeCategory || "all"} onValueChange={value => onChange("includeCategory", value === "all" ? "" : value)}>
                    <SelectTrigger id={includeCategoryFieldId} className="mt-1">
                        <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="all">{t("labels.includeCategoryOptions.all")}</SelectItem>
                    </SelectContent>
                </Select>
            </div>

            <div className={styles.settingsSeparator}>
                <HelpCallout
                    labelId={excludeCategoryId}
                    fieldId={excludeCategoryFieldId}
                    helpText={t("helpTexts.excludeCategory")}
                    label={t("labels.excludeCategory")}
                />
                <Input
                    id={excludeCategoryFieldId}
                    className="mt-1"
                    defaultValue={excludeCategory}
                    onChange={e => onChange("excludeCategory", e.target.value || "")}
                />
            </div>

            {showSemanticRankerOption && !useAgenticKnowledgeBase && (
                <>
                    <div className={styles.settingsSeparator}>
                        <HelpCallout
                            labelId={semanticRankerId}
                            fieldId={semanticRankerFieldId}
                            helpText={t("helpTexts.useSemanticReranker")}
                            label={t("labels.useSemanticRanker")}
                        />
                        <div className="flex items-center gap-2 mt-1">
                            <Checkbox
                                id={semanticRankerFieldId}
                                checked={useSemanticRanker}
                                onCheckedChange={checked => onChange("useSemanticRanker", !!checked)}
                            />
                        </div>
                    </div>

                    <div className={styles.settingsSeparator}>
                        <HelpCallout
                            labelId={semanticCaptionsId}
                            fieldId={semanticCaptionsFieldId}
                            helpText={t("helpTexts.useSemanticCaptions")}
                            label={t("labels.useSemanticCaptions")}
                        />
                        <div className="flex items-center gap-2 mt-1">
                            <Checkbox
                                id={semanticCaptionsFieldId}
                                checked={useSemanticCaptions}
                                onCheckedChange={checked => onChange("useSemanticCaptions", !!checked)}
                                disabled={!useSemanticRanker}
                            />
                        </div>
                    </div>
                </>
            )}

            {showQueryRewritingOption && !useAgenticKnowledgeBase && (
                <div className={styles.settingsSeparator}>
                    <HelpCallout
                        labelId={queryRewritingFieldId}
                        fieldId={queryRewritingFieldId}
                        helpText={t("helpTexts.useQueryRewriting")}
                        label={t("labels.useQueryRewriting")}
                    />
                    <div className="flex items-center gap-2 mt-1">
                        <Checkbox
                            id={queryRewritingFieldId}
                            checked={useQueryRewriting}
                            onCheckedChange={checked => onChange("useQueryRewriting", !!checked)}
                            disabled={!useSemanticRanker}
                        />
                    </div>
                </div>
            )}

            {showReasoningEffortOption && (
                <div className={styles.settingsSeparator}>
                    <HelpCallout
                        labelId={reasoningEffortFieldId}
                        fieldId={reasoningEffortFieldId}
                        helpText={t("helpTexts.reasoningEffort")}
                        label={t("labels.reasoningEffort")}
                    />
                    <Select value={reasoningEffort} onValueChange={value => onChange("reasoningEffort", value)}>
                        <SelectTrigger id={reasoningEffortFieldId} className="mt-1">
                            <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="minimal">{t("labels.reasoningEffortOptions.minimal")}</SelectItem>
                            <SelectItem value="low">{t("labels.reasoningEffortOptions.low")}</SelectItem>
                            <SelectItem value="medium">{t("labels.reasoningEffortOptions.medium")}</SelectItem>
                            <SelectItem value="high">{t("labels.reasoningEffortOptions.high")}</SelectItem>
                        </SelectContent>
                    </Select>
                </div>
            )}

            {showVectorOption && !useAgenticKnowledgeBase && (
                <VectorSettings
                    defaultRetrievalMode={retrievalMode}
                    defaultSearchTextEmbeddings={searchTextEmbeddings}
                    defaultSearchImageEmbeddings={searchImageEmbeddings}
                    showImageOptions={showMultimodalOptions}
                    updateRetrievalMode={val => onChange("retrievalMode", val)}
                    updateSearchTextEmbeddings={val => onChange("searchTextEmbeddings", val)}
                    updateSearchImageEmbeddings={val => onChange("searchImageEmbeddings", val)}
                />
            )}

            {!useWebSource && (
                <>
                    <h3 className={styles.sectionHeader}>{t("llmSettings")}</h3>
                    <div className={styles.settingsSeparator}>
                        <HelpCallout
                            labelId={promptTemplateId}
                            fieldId={promptTemplateFieldId}
                            helpText={t("helpTexts.promptTemplate")}
                            label={t("labels.promptTemplate")}
                        />
                        <Textarea
                            id={promptTemplateFieldId}
                            className="mt-1"
                            defaultValue={promptTemplate}
                            onChange={e => onChange("promptTemplate", e.target.value || "")}
                        />
                    </div>

                    <div className={styles.settingsSeparator}>
                        <HelpCallout
                            labelId={temperatureId}
                            fieldId={temperatureFieldId}
                            helpText={t("helpTexts.temperature")}
                            label={t("labels.temperature")}
                        />
                        <Input
                            id={temperatureFieldId}
                            className="mt-1"
                            type="number"
                            min={0}
                            max={1}
                            step={0.1}
                            defaultValue={temperature.toString()}
                            onChange={e => onChange("temperature", parseFloat(e.target.value || "0"))}
                        />
                    </div>

                    <div className={styles.settingsSeparator}>
                        <HelpCallout labelId={seedId} fieldId={seedFieldId} helpText={t("helpTexts.seed")} label={t("labels.seed")} />
                        <Input
                            id={seedFieldId}
                            className="mt-1"
                            type="text"
                            defaultValue={seed?.toString() || ""}
                            onChange={e => onChange("seed", e.target.value ? parseInt(e.target.value) : null)}
                        />
                    </div>

                    {showMultimodalOptions && !useAgenticKnowledgeBase && (
                        <fieldset className={styles.fieldset + " " + styles.settingsSeparator}>
                            <legend className={styles.legend}>{t("labels.llmInputs")}</legend>
                            <div className="flex flex-col gap-2">
                                <div>
                                    <HelpCallout
                                        labelId="sendTextSourcesLabel"
                                        fieldId="sendTextSources"
                                        helpText={t("helpTexts.llmTextInputs")}
                                        label={t("labels.llmInputsOptions.texts")}
                                    />
                                    <div className="flex items-center gap-2 mt-1">
                                        <Checkbox
                                            id="sendTextSources"
                                            checked={sendTextSources}
                                            onCheckedChange={checked => onChange("sendTextSources", !!checked)}
                                        />
                                    </div>
                                </div>
                                <div>
                                    <HelpCallout
                                        labelId="sendImageSourcesLabel"
                                        fieldId="sendImageSources"
                                        helpText={t("helpTexts.llmImageInputs")}
                                        label={t("labels.llmInputsOptions.images")}
                                    />
                                    <div className="flex items-center gap-2 mt-1">
                                        <Checkbox
                                            id="sendImageSources"
                                            checked={sendImageSources}
                                            onCheckedChange={checked => onChange("sendImageSources", !!checked)}
                                        />
                                    </div>
                                </div>
                            </div>
                        </fieldset>
                    )}
                </>
            )}
        </div>
    );
};
