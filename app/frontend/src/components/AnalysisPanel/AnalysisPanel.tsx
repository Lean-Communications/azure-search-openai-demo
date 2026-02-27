import { useMsal } from "@azure/msal-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import DOMPurify from "dompurify";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { ChatAppResponse, getHeaders } from "../../api";
import { getToken, useLogin } from "../../authConfig";
import { MarkdownViewer } from "../MarkdownViewer";
import { SupportingContent } from "../SupportingContent";
import styles from "./AnalysisPanel.module.css";
import { AnalysisPanelTabs } from "./AnalysisPanelTabs";
import { ThoughtProcess } from "./ThoughtProcess";

interface Props {
    className: string;
    activeTab: AnalysisPanelTabs;
    onActiveTabChanged: (tab: AnalysisPanelTabs) => void;
    activeCitation: string | undefined;
    citationHeight: string;
    answer: ChatAppResponse;
    onCitationClicked?: (citationFilePath: string) => void;
}

export const AnalysisPanel = ({ answer, activeTab, activeCitation, citationHeight, className, onActiveTabChanged, onCitationClicked }: Props) => {
    const isDisabledThoughtProcessTab: boolean = !answer.context.thoughts;
    const dataPoints = answer.context.data_points;
    const hasSupportingContent = Boolean(
        dataPoints &&
            ((dataPoints.text && dataPoints.text.length > 0) ||
                (dataPoints.images && dataPoints.images.length > 0) ||
                (dataPoints.external_results_metadata && dataPoints.external_results_metadata.length > 0))
    );
    const isDisabledSupportingContentTab: boolean = !hasSupportingContent;
    const isDisabledCitationTab: boolean = !activeCitation;
    const [citation, setCitation] = useState("");

    const client = useLogin ? useMsal().instance : undefined;
    const { t } = useTranslation();

    const fetchCitation = async () => {
        const token = client ? await getToken(client) : undefined;
        if (activeCitation) {
            const originalHash = activeCitation.indexOf("#") ? activeCitation.split("#")[1] : "";
            const response = await fetch(activeCitation, {
                method: "GET",
                headers: await getHeaders(token)
            });
            const citationContent = await response.blob();
            let citationObjectUrl = URL.createObjectURL(citationContent);
            if (originalHash) {
                citationObjectUrl += "#" + originalHash;
            }
            setCitation(citationObjectUrl);
        }
    };
    useEffect(() => {
        fetchCitation();
    }, [activeCitation]);

    const renderFileViewer = () => {
        if (!activeCitation) {
            return null;
        }

        const urlWithoutHash = activeCitation.split("#")[0];
        const fileExtension = urlWithoutHash.split(".").pop()?.toLowerCase();

        switch (fileExtension) {
            case "png":
            case "jpg":
            case "jpeg":
                return <img src={citation} className={styles.citationImg} alt="Citation Image" />;
            case "md":
                return <MarkdownViewer src={activeCitation} />;
            case "pptx":
            case "docx": {
                const citationRef = activeCitation.replace(/^\/content\//, "");
                const textItems = answer.context.data_points?.text ?? [];
                const matchingChunks = textItems
                    .filter(item => item.startsWith(citationRef + ": "))
                    .map(item => {
                        const content = item.substring(item.indexOf(": ") + 2);
                        return DOMPurify.sanitize(content);
                    });

                if (matchingChunks.length > 0) {
                    return (
                        <div className={styles.citationContent}>
                            {matchingChunks.map((html, i) => (
                                <div key={i} dangerouslySetInnerHTML={{ __html: html }} />
                            ))}
                        </div>
                    );
                }
                return <iframe title="Citation" src={citation} width="100%" height={citationHeight} />;
            }
            default:
                return <iframe title="Citation" src={citation} width="100%" height={citationHeight} />;
        }
    };

    return (
        <Tabs
            className={className}
            value={activeTab}
            onValueChange={value => onActiveTabChanged(value as AnalysisPanelTabs)}
        >
            <TabsList>
                <TabsTrigger value={AnalysisPanelTabs.ThoughtProcessTab} disabled={isDisabledThoughtProcessTab}>
                    {t("headerTexts.thoughtProcess")}
                </TabsTrigger>
                <TabsTrigger value={AnalysisPanelTabs.SupportingContentTab} disabled={isDisabledSupportingContentTab}>
                    {t("headerTexts.supportingContent")}
                </TabsTrigger>
                <TabsTrigger value={AnalysisPanelTabs.CitationTab} disabled={isDisabledCitationTab}>
                    {t("headerTexts.citation")}
                </TabsTrigger>
            </TabsList>
            <TabsContent value={AnalysisPanelTabs.ThoughtProcessTab}>
                <ThoughtProcess thoughts={answer.context.thoughts || []} onCitationClicked={onCitationClicked} />
            </TabsContent>
            <TabsContent value={AnalysisPanelTabs.SupportingContentTab}>
                <SupportingContent supportingContent={answer.context.data_points} />
            </TabsContent>
            <TabsContent value={AnalysisPanelTabs.CitationTab}>
                {renderFileViewer()}
            </TabsContent>
        </Tabs>
    );
};
