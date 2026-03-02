import base64

from prepdocslib.page import ImageOnPage


def _make_image(**kwargs) -> ImageOnPage:
    """Helper to create an ImageOnPage with sensible defaults, overridden by kwargs."""
    defaults = {
        "bytes": b"fake-image-bytes",
        "bbox": (0, 0, 100, 100),
        "filename": "slide_1.png",
        "figure_id": "fig_1",
        "page_num": 0,
        "placeholder": '<figure id="fig_1"></figure>',
    }
    defaults.update(kwargs)
    return ImageOnPage(**defaults)


class TestImageOnPageContextFields:
    def test_image_on_page_context_fields(self):
        """Verify the new context fields can be set via the constructor."""
        image = _make_image(
            context_title="Slide Title",
            context_text="Full text of the slide",
            alt_text="A bar chart showing revenue growth",
            source_document_summary="Q3 earnings presentation",
        )
        assert image.context_title == "Slide Title"
        assert image.context_text == "Full text of the slide"
        assert image.alt_text == "A bar chart showing revenue growth"
        assert image.source_document_summary == "Q3 earnings presentation"

    def test_image_on_page_context_fields_default_none(self):
        """Verify all new context fields default to None when not provided."""
        image = _make_image()
        assert image.context_title is None
        assert image.context_text is None
        assert image.alt_text is None
        assert image.source_document_summary is None

    def test_image_on_page_skill_payload_roundtrip(self):
        """Verify to_skill_payload / from_skill_payload roundtrip preserves new fields."""
        original = _make_image(
            context_title="Introduction",
            context_text="Welcome to the presentation about AI.",
            alt_text="Company logo",
            source_document_summary="AI strategy overview deck",
            description="An image of a company logo",
        )
        doc_name = "presentation.pptx"

        # Serialize
        payload = original.to_skill_payload(doc_name)

        # Verify new fields appear in payload
        assert payload["context_title"] == "Introduction"
        assert payload["context_text"] == "Welcome to the presentation about AI."
        assert payload["alt_text"] == "Company logo"
        assert payload["source_document_summary"] == "AI strategy overview deck"
        assert payload["document_file_name"] == doc_name

        # Deserialize
        restored, restored_doc_name = ImageOnPage.from_skill_payload(payload)

        assert restored_doc_name == doc_name
        assert restored.context_title == original.context_title
        assert restored.context_text == original.context_text
        assert restored.alt_text == original.alt_text
        assert restored.source_document_summary == original.source_document_summary
        assert restored.description == original.description
        assert restored.filename == original.filename
        assert restored.figure_id == original.figure_id
        assert restored.page_num == original.page_num

    def test_image_on_page_skill_payload_roundtrip_none_fields(self):
        """Verify roundtrip works when context fields are None (not present in payload)."""
        original = _make_image()
        payload = original.to_skill_payload("doc.pdf")

        restored, _ = ImageOnPage.from_skill_payload(payload)

        assert restored.context_title is None
        assert restored.context_text is None
        assert restored.alt_text is None
        assert restored.source_document_summary is None
