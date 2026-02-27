import { useTranslation } from "react-i18next";
import React, { useState, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Loader2, Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";

import styles from "./MarkdownViewer.module.css";

interface MarkdownViewerProps {
    src: string;
}

export const MarkdownViewer: React.FC<MarkdownViewerProps> = ({ src }) => {
    const [content, setContent] = useState<string>("");
    const [isLoading, setIsLoading] = useState<boolean>(true);
    const [error, setError] = useState<Error | null>(null);
    const { t } = useTranslation();

    const removeAnchorLinks = (markdown: string) => {
        const ancorLinksRegex = /\[.*?\]\(#.*?\)/g;
        return markdown.replace(ancorLinksRegex, "");
    };

    useEffect(() => {
        const fetchMarkdown = async () => {
            try {
                const response = await fetch(src);

                if (!response.ok) {
                    throw new Error("Failed loading markdown file.");
                }

                let markdownText = await response.text();
                markdownText = removeAnchorLinks(markdownText);
                setContent(markdownText);
            } catch (error: any) {
                setError(error);
            } finally {
                setIsLoading(false);
            }
        };

        fetchMarkdown();
    }, [src]);

    return (
        <div>
            {isLoading ? (
                <div className={`${styles.loading} ${styles.markdownViewer}`}>
                    <Loader2 className="h-8 w-8 animate-spin" />
                    <span className="ml-2">Loading file</span>
                </div>
            ) : error ? (
                <div className={`${styles.error} ${styles.markdownViewer}`}>
                    <Alert variant="destructive">
                        <AlertDescription>
                            {error.message}{" "}
                            <a href={src} download className="underline">
                                Download the file
                            </a>
                        </AlertDescription>
                    </Alert>
                </div>
            ) : (
                <div>
                    <a href={src} download className={styles.downloadButton}>
                        <Button variant="ghost" size="icon" title={t("tooltips.save")} aria-label={t("tooltips.save")}>
                            <Download className="h-5 w-5" />
                        </Button>
                    </a>
                    <ReactMarkdown children={content} remarkPlugins={[remarkGfm]} className={`${styles.markdown} ${styles.markdownViewer}`} />
                </div>
            )}
        </div>
    );
};
