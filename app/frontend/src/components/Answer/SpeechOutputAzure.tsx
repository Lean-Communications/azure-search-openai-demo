import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Volume2, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { getSpeechApi, SpeechConfig } from "../../api";

interface Props {
    answer: string;
    speechConfig: SpeechConfig;
    index: number;
    isStreaming: boolean;
}

export const SpeechOutputAzure = ({ answer, speechConfig, index, isStreaming }: Props) => {
    const [isLoading, setIsLoading] = useState(false);
    const [localPlayingState, setLocalPlayingState] = useState(false);
    const { t } = useTranslation();

    const playAudio = async (url: string) => {
        speechConfig.audio.src = url;
        await speechConfig.audio
            .play()
            .then(() => {
                speechConfig.audio.onended = () => {
                    speechConfig.setIsPlaying(false);
                    setLocalPlayingState(false);
                };
                speechConfig.setIsPlaying(true);
                setLocalPlayingState(true);
            })
            .catch(() => {
                alert("Failed to play speech output.");
                console.error("Failed to play speech output.");
                speechConfig.setIsPlaying(false);
                setLocalPlayingState(false);
            });
    };

    const startOrStopSpeech = async (answer: string) => {
        if (speechConfig.isPlaying) {
            speechConfig.audio.pause();
            speechConfig.audio.currentTime = 0;
            speechConfig.setIsPlaying(false);
            setLocalPlayingState(false);
            return;
        }
        if (speechConfig.speechUrls[index]) {
            playAudio(speechConfig.speechUrls[index]);
            return;
        }
        setIsLoading(true);
        await getSpeechApi(answer).then(async speechUrl => {
            if (!speechUrl) {
                alert("Speech output is not available.");
                console.error("Speech output is not available.");
                return;
            }
            setIsLoading(false);
            speechConfig.setSpeechUrls(speechConfig.speechUrls.map((url, i) => (i === index ? speechUrl : url)));
            playAudio(speechUrl);
        });
    };

    const color = localPlayingState ? "text-red-500" : "text-black";

    return isLoading ? (
        <Button variant="ghost" size="icon" title="Loading speech" aria-label="Loading speech" disabled>
            <Loader2 className={`h-5 w-5 animate-spin ${color}`} />
        </Button>
    ) : (
        <Button
            variant="ghost"
            size="icon"
            className={color}
            title={t("tooltips.speakAnswer")}
            aria-label={t("tooltips.speakAnswer")}
            onClick={() => startOrStopSpeech(answer)}
            disabled={isStreaming}
        >
            <Volume2 className="h-5 w-5" />
        </Button>
    );
};
