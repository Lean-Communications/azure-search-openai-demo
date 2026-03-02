import DOMPurify from "dompurify";

type ParsedSupportingContentItem = {
    title: string;
    content: string;
};

/**
 * Rewrites Azure Storage image URLs in HTML to use the /content/ proxy route.
 * Handles both Blob Storage (.blob.) and Data Lake (.dfs.) endpoints.
 * e.g. https://account.blob.core.windows.net/container/path → /content/path
 */
export function rewriteBlobImageUrls(html: string): string {
    return html.replace(/https?:\/\/[^/]+\.(?:blob|dfs)\.core\.windows\.net\/[^/"']+\/([^"']+)/g, "/content/$1");
}

export function parseSupportingContentItem(item: string): ParsedSupportingContentItem {
    // Assumes the item starts with the file name followed by : and the content.
    // Example: "sdp_corporate.pdf: this is the content that follows".
    const parts = item.split(": ");
    const title = parts[0];
    const content = DOMPurify.sanitize(rewriteBlobImageUrls(parts.slice(1).join(": ")));

    return {
        title,
        content
    };
}
