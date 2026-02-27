import { useMsal } from "@azure/msal-react";
import { getToken, useLogin } from "../../authConfig";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Loader2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { HistoryData, HistoryItem } from "../HistoryItem";
import { Answers, HistoryProviderOptions } from "../HistoryProviders/IProvider";
import { useHistoryManager, HistoryMetaData } from "../HistoryProviders";
import { useTranslation } from "react-i18next";
import styles from "./HistoryPanel.module.css";

const HISTORY_COUNT_PER_LOAD = 20;

export const HistoryPanel = ({
    provider,
    isOpen,
    notify,
    onClose,
    onChatSelected
}: {
    provider: HistoryProviderOptions;
    isOpen: boolean;
    notify: boolean;
    onClose: () => void;
    onChatSelected: (answers: Answers) => void;
}) => {
    const historyManager = useHistoryManager(provider);
    const [history, setHistory] = useState<HistoryMetaData[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [hasMoreHistory, setHasMoreHistory] = useState(false);

    const client = useLogin ? useMsal().instance : undefined;

    useEffect(() => {
        if (!isOpen) return;
        if (notify) {
            setHistory([]);
            historyManager.resetContinuationToken();
            setHasMoreHistory(true);
        }
    }, [isOpen, notify]);

    const loadMoreHistory = async () => {
        setIsLoading(() => true);
        const token = client ? await getToken(client) : undefined;
        const items = await historyManager.getNextItems(HISTORY_COUNT_PER_LOAD, token);
        if (items.length === 0) {
            setHasMoreHistory(false);
        }
        setHistory(prevHistory => [...prevHistory, ...items]);
        setIsLoading(() => false);
    };

    const handleSelect = async (id: string) => {
        const token = client ? await getToken(client) : undefined;
        const item = await historyManager.getItem(id, token);
        if (item) {
            onChatSelected(item);
        }
    };

    const handleDelete = async (id: string) => {
        const token = client ? await getToken(client) : undefined;
        await historyManager.deleteItem(id, token);
        setHistory(prevHistory => prevHistory.filter(item => item.id !== id));
    };

    const groupedHistory = useMemo(() => groupHistory(history), [history]);

    const { t } = useTranslation();

    const handleOpenChange = (open: boolean) => {
        if (!open) {
            onClose();
            setHistory([]);
            setHasMoreHistory(true);
            historyManager.resetContinuationToken();
        }
    };

    return (
        <Sheet open={isOpen} onOpenChange={handleOpenChange}>
            <SheetContent side="left" className="w-[300px] p-0 overflow-y-auto">
                <SheetHeader className="p-4">
                    <SheetTitle>{t("history.chatHistory")}</SheetTitle>
                </SheetHeader>
                <div className="px-4 pb-4">
                    {Object.entries(groupedHistory).map(([group, items]) => (
                        <div key={group} className={styles.group}>
                            <p className={styles.groupLabel}>{t(group)}</p>
                            {items.map(item => (
                                <HistoryItem key={item.id} item={item} onSelect={handleSelect} onDelete={handleDelete} />
                            ))}
                        </div>
                    ))}
                    {isLoading && (
                        <div className="flex justify-center mt-2.5">
                            <Loader2 className="h-6 w-6 animate-spin" />
                        </div>
                    )}
                    {history.length === 0 && !isLoading && <p>{t("history.noHistory")}</p>}
                    {hasMoreHistory && !isLoading && <InfiniteLoadingButton func={loadMoreHistory} />}
                </div>
            </SheetContent>
        </Sheet>
    );
};

function groupHistory(history: HistoryData[]) {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    const lastWeek = new Date(today);
    lastWeek.setDate(lastWeek.getDate() - 7);
    const lastMonth = new Date(today);
    lastMonth.setDate(lastMonth.getDate() - 30);

    return history.reduce(
        (groups, item) => {
            const itemDate = new Date(item.timestamp);
            let group;

            if (itemDate >= today) {
                group = "history.today";
            } else if (itemDate >= yesterday) {
                group = "history.yesterday";
            } else if (itemDate >= lastWeek) {
                group = "history.last7days";
            } else if (itemDate >= lastMonth) {
                group = "history.last30days";
            } else {
                group = itemDate.toLocaleDateString(undefined, { year: "numeric", month: "long" });
            }

            if (!groups[group]) {
                groups[group] = [];
            }
            groups[group].push(item);
            return groups;
        },
        {} as Record<string, HistoryData[]>
    );
}

const InfiniteLoadingButton = ({ func }: { func: () => void }) => {
    const buttonRef = useRef(null);

    useEffect(() => {
        const observer = new IntersectionObserver(
            entries => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        if (buttonRef.current) {
                            func();
                        }
                    }
                });
            },
            {
                root: null,
                threshold: 0
            }
        );

        if (buttonRef.current) {
            observer.observe(buttonRef.current);
        }

        return () => {
            if (buttonRef.current) {
                observer.unobserve(buttonRef.current);
            }
        };
    }, []);

    return <button ref={buttonRef} onClick={func} />;
};
