import React, { useState, ChangeEvent } from "react";
import { Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useMsal } from "@azure/msal-react";
import { useTranslation } from "react-i18next";

import { SimpleAPIResponse, uploadFileApi, deleteUploadedFileApi, listUploadedFilesApi } from "../../api";
import { useLogin, getToken } from "../../authConfig";
import styles from "./UploadFile.module.css";

interface Props {
    className?: string;
    disabled?: boolean;
}

export const UploadFile: React.FC<Props> = ({ className, disabled }: Props) => {
    const [isCalloutVisible, setIsCalloutVisible] = useState<boolean>(false);
    const [isUploading, setIsUploading] = useState<boolean>(false);
    const [isLoading, setIsLoading] = useState<boolean>(true);
    const [deletionStatus, setDeletionStatus] = useState<{ [filename: string]: "pending" | "error" | "success" }>({});
    const [uploadedFile, setUploadedFile] = useState<SimpleAPIResponse>();
    const [uploadedFileError, setUploadedFileError] = useState<string>();
    const [uploadedFiles, setUploadedFiles] = useState<string[]>([]);
    const { t } = useTranslation();

    if (!useLogin) {
        throw new Error("The UploadFile component requires useLogin to be true");
    }

    const client = useMsal().instance;

    const handleButtonClick = async () => {
        setIsCalloutVisible(!isCalloutVisible);

        try {
            const idToken = await getToken(client);
            if (!idToken) {
                throw new Error("No authentication token available");
            }
            listUploadedFiles(idToken);
        } catch (error) {
            console.error(error);
            setIsLoading(false);
        }
    };

    const listUploadedFiles = async (idToken: string) => {
        listUploadedFilesApi(idToken).then(files => {
            setIsLoading(false);
            setDeletionStatus({});
            setUploadedFiles(files);
        });
    };

    const handleRemoveFile = async (filename: string) => {
        setDeletionStatus({ ...deletionStatus, [filename]: "pending" });

        try {
            const idToken = await getToken(client);
            if (!idToken) {
                throw new Error("No authentication token available");
            }

            await deleteUploadedFileApi(filename, idToken);
            setDeletionStatus({ ...deletionStatus, [filename]: "success" });
            listUploadedFiles(idToken);
        } catch (error) {
            setDeletionStatus({ ...deletionStatus, [filename]: "error" });
            console.error(error);
        }
    };

    const handleUploadFile = async (e: ChangeEvent<HTMLInputElement>) => {
        e.preventDefault();
        if (!e.target.files || e.target.files.length === 0) {
            return;
        }
        setIsUploading(true);
        const file: File = e.target.files[0];
        const formData = new FormData();
        formData.append("file", file);

        try {
            const idToken = await getToken(client);
            if (!idToken) {
                throw new Error("No authentication token available");
            }
            const response: SimpleAPIResponse = await uploadFileApi(formData, idToken);
            setUploadedFile(response);
            setIsUploading(false);
            setUploadedFileError(undefined);
            listUploadedFiles(idToken);
        } catch (error) {
            console.error(error);
            setIsUploading(false);
            setUploadedFileError(t("upload.uploadedFileError"));
        }
    };

    return (
        <div className={`${styles.container} ${className ?? ""}`}>
            <Popover open={isCalloutVisible} onOpenChange={setIsCalloutVisible}>
                <PopoverTrigger asChild>
                    <Button variant="outline" disabled={disabled} onClick={handleButtonClick}>
                        <Plus className="h-5 w-5" />
                        {t("upload.manageFileUploads")}
                    </Button>
                </PopoverTrigger>
                <PopoverContent className={`${styles.callout} w-80`}>
                    <form encType="multipart/form-data">
                        <div>
                            <Label>{t("upload.fileLabel")}</Label>
                            <input
                                accept=".txt, .md, .json, .png, .jpg, .jpeg, .bmp, .heic, .tiff, .pdf, .docx, .xlsx, .pptx, .html"
                                className={styles.chooseFiles}
                                type="file"
                                onChange={handleUploadFile}
                            />
                        </div>
                    </form>

                    {isUploading && <p className="text-sm">{t("upload.uploadingFiles")}</p>}
                    {!isUploading && uploadedFileError && <p className="text-sm text-red-500">{uploadedFileError}</p>}
                    {!isUploading && uploadedFile && <p className="text-sm">{uploadedFile.message}</p>}

                    <h3 className="font-semibold mt-2">{t("upload.uploadedFilesLabel")}</h3>

                    {isLoading && <p className="text-sm">{t("upload.loading")}</p>}
                    {!isLoading && uploadedFiles.length === 0 && <p className="text-sm">{t("upload.noFilesUploaded")}</p>}
                    {uploadedFiles.map((filename, index) => {
                        return (
                            <div key={index} className={styles.list}>
                                <div className={styles.item}>{filename}</div>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => handleRemoveFile(filename)}
                                    disabled={deletionStatus[filename] === "pending" || deletionStatus[filename] === "success"}
                                >
                                    <Trash2 className="h-4 w-4" />
                                    {!deletionStatus[filename] && t("upload.deleteFile")}
                                    {deletionStatus[filename] == "pending" && t("upload.deletingFile")}
                                    {deletionStatus[filename] == "error" && t("upload.errorDeleting")}
                                    {deletionStatus[filename] == "success" && t("upload.fileDeleted")}
                                </Button>
                            </div>
                        );
                    })}
                </PopoverContent>
            </Popover>
        </div>
    );
};
