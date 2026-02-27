import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Info } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

interface IHelpCalloutProps {
    label: string | undefined;
    labelId: string;
    fieldId: string | undefined;
    helpText: string;
}

export const HelpCallout = (props: IHelpCalloutProps): JSX.Element => {
    const { t } = useTranslation();

    return (
        <div className="flex items-center gap-1 max-w-[300px]">
            <label id={props.labelId} htmlFor={props.fieldId}>
                {props.label}
            </label>
            <Popover>
                <PopoverTrigger asChild>
                    <Button variant="ghost" size="icon" className="h-6 w-6 -mb-0.5" title={t("tooltips.info")} aria-label={t("tooltips.info")}>
                        <Info className="h-4 w-4" />
                    </Button>
                </PopoverTrigger>
                <PopoverContent className="max-w-[300px]">
                    <p className="text-sm">{props.helpText}</p>
                </PopoverContent>
            </Popover>
        </div>
    );
};
