"""Extract embedded images from PPTX and DOCX files and merge them into parsed Pages.

Uses python-pptx and python-docx to iterate through shapes/paragraphs,
extract raster images, and create ImageOnPage objects that the downstream
figure-processing pipeline (GPT-4o description, blob upload, etc.) already handles.
"""

import hashlib
import io
import logging
import os

from PIL import Image

from .page import ImageOnPage, Page

logger = logging.getLogger(__name__)

# Filtering thresholds
_MIN_IMAGE_BYTES = 2048  # 2 KB — skip tiny icons/spacers
_MIN_IMAGE_DIMENSION = 50  # px — skip bullets and decorations
_SKIP_FORMATS = {"emf", "wmf", "x-emf", "x-wmf"}

# Map common Office image content-types to extensions
_MIME_TO_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/tiff": ".tiff",
    "image/bmp": ".bmp",
}


def _should_skip_image(image_bytes: bytes, content_type: str) -> bool:
    """Return True if the image should be filtered out."""
    subtype = content_type.split("/")[-1].lower() if "/" in content_type else content_type.lower()
    if subtype in _SKIP_FORMATS:
        return True

    if len(image_bytes) < _MIN_IMAGE_BYTES:
        return True

    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            w, h = img.size
            if w < _MIN_IMAGE_DIMENSION or h < _MIN_IMAGE_DIMENSION:
                return True
    except Exception:
        pass

    return False


def _find_page_for_offset(char_offset: int, pages: list[Page]) -> int:
    """Find which page a character offset belongs to."""
    for i in range(len(pages) - 1, -1, -1):
        if char_offset >= pages[i].offset:
            return pages[i].page_num
    return pages[0].page_num if pages else 0


def _extract_pptx_images(document_bytes: bytes, filename: str) -> list[ImageOnPage]:
    """Extract images from a PPTX file, one per slide shape."""
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    prs = Presentation(io.BytesIO(document_bytes))
    images: list[ImageOnPage] = []
    seen_hashes: set[str] = set()
    img_counter = 0

    for slide_idx, slide in enumerate(prs.slides):
        for shape in slide.shapes:
            if shape.shape_type != MSO_SHAPE_TYPE.PICTURE:
                continue

            image_blob = shape.image.blob
            content_type = shape.image.content_type or "image/png"

            if _should_skip_image(image_blob, content_type):
                continue

            img_hash = hashlib.sha256(image_blob).hexdigest()
            if img_hash in seen_hashes:
                continue
            seen_hashes.add(img_hash)

            img_counter += 1
            figure_id = f"img_{img_counter}"
            ext = _MIME_TO_EXT.get(content_type, ".png")
            base = os.path.splitext(filename)[0]
            img_filename = f"{base}_{figure_id}{ext}"
            placeholder = f'<figure id="{figure_id}"></figure>'

            images.append(
                ImageOnPage(
                    bytes=image_blob,
                    bbox=(0, 0, 0, 0),
                    filename=img_filename,
                    figure_id=figure_id,
                    page_num=slide_idx,
                    placeholder=placeholder,
                    mime_type=content_type,
                )
            )

    return images


def _extract_docx_images(document_bytes: bytes, filename: str, pages: list[Page]) -> list[ImageOnPage]:
    """Extract inline images from a DOCX file, resolving page numbers from parsed pages."""
    from docx import Document
    from docx.opc.constants import RELATIONSHIP_TYPE as RT

    doc = Document(io.BytesIO(document_bytes))
    images: list[ImageOnPage] = []
    seen_hashes: set[str] = set()
    img_counter = 0

    # Build cumulative character offsets per paragraph to match against Page.offset ranges
    paragraph_offsets: list[int] = []
    cumulative = 0
    for para in doc.paragraphs:
        paragraph_offsets.append(cumulative)
        cumulative += len(para.text) + 1  # +1 for implicit newline

    for para_idx, para in enumerate(doc.paragraphs):
        blips = para._element.findall(
            ".//{http://schemas.openxmlformats.org/drawingml/2006/main}blip"
        )
        for blip in blips:
            embed_id = blip.get(
                "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"
            )
            if not embed_id:
                continue

            try:
                rel = para.part.rels[embed_id]
            except KeyError:
                continue

            if rel.reltype != RT.IMAGE:
                continue

            image_blob = rel.target_part.blob
            content_type = rel.target_part.content_type or "image/png"

            if _should_skip_image(image_blob, content_type):
                continue

            img_hash = hashlib.sha256(image_blob).hexdigest()
            if img_hash in seen_hashes:
                continue
            seen_hashes.add(img_hash)

            img_counter += 1
            figure_id = f"img_{img_counter}"
            ext = _MIME_TO_EXT.get(content_type, ".png")
            base = os.path.splitext(filename)[0]
            img_filename = f"{base}_{figure_id}{ext}"
            placeholder = f'<figure id="{figure_id}"></figure>'

            para_offset = paragraph_offsets[para_idx]
            page_num = _find_page_for_offset(para_offset, pages) if pages else 0

            images.append(
                ImageOnPage(
                    bytes=image_blob,
                    bbox=(0, 0, 0, 0),
                    filename=img_filename,
                    figure_id=figure_id,
                    page_num=page_num,
                    placeholder=placeholder,
                    mime_type=content_type,
                )
            )

    return images


def extract_and_merge_office_images(filename: str, document_bytes: bytes, pages: list[Page]) -> list[Page]:
    """Extract embedded images from PPTX/DOCX and merge them into existing pages.

    Creates ImageOnPage objects with placeholders, appends placeholders to page text,
    and adds images to the corresponding Page.images list. The downstream pipeline
    (GPT-4o description, blob upload, placeholder replacement) handles the rest.

    Args:
        filename: Original document filename (e.g. "slides.pptx")
        document_bytes: Raw file bytes
        pages: Parsed pages from Document Intelligence

    Returns:
        The same pages list, mutated with extracted images.
    """
    ext = os.path.splitext(filename)[1].lower()

    if ext == ".pptx":
        images = _extract_pptx_images(document_bytes, filename)
    elif ext == ".docx":
        images = _extract_docx_images(document_bytes, filename, pages)
    else:
        return pages

    if not images:
        logger.info("No extractable images found in %s", filename)
        return pages

    logger.info("Extracted %d images from %s", len(images), filename)

    # Build a lookup of page_num → Page for fast assignment
    page_map: dict[int, Page] = {p.page_num: p for p in pages}

    for image in images:
        target_page = page_map.get(image.page_num)
        if target_page is None:
            # Fall back to the last page if the image's page_num doesn't match
            target_page = pages[-1] if pages else None
            if target_page is None:
                continue

        # Append placeholder to end of page text
        target_page.text = target_page.text.rstrip() + "\n" + image.placeholder
        target_page.images.append(image)

    return pages
