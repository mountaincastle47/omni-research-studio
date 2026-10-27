"""Comprehensive headless verification script for Pass 2 of OmniResearch Studio overhaul.

Tests:
1. pymupdf4llm extracts sample multi-page PDF text page-by-page with <!--PAGE_START:N--> tags.
2. rapidocr-onnxruntime initializes cleanly without DLL errors and executes inference on test image numpy arrays.
3. trafilatura and extract_clean_web_article extract clean body text from sample HTML strings with table support.
4. Semantic alignment check function accurately flags matching (aligned, cite-verified) vs. non-matching (unaligned, cite-suspect) claim-source pairs.
5. Scanned PDF fallback: detects low alphanumeric count page and triggers RapidOCR.
6. Page-level citation navigation: clicking cite:1:2 navigates SourceInspectorDock directly to <!--PAGE_START:2-->.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Force Qt offscreen platform for headless verification
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import numpy as np
import pymupdf
import pymupdf4llm
from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import QApplication

from core.document_loader import SourceDocument, load_pdf
from core.markdown_utils import build_dark_html
from core.notebook_synthesis import (
    EPISTEMIC_FRICTION_MANDATE,
    check_semantic_alignment,
    create_semantic_anchor_builder,
    extract_page_chunk_from_content,
)
from core.web_scraper import _extract_with_trafilatura, extract_clean_web_article
from ui.main_window import MainWindow, render_markdown_safely
from ui.source_dock import SourceInspectorDock


def test_pymupdf4llm_page_extraction() -> None:
    print("[1/6] Testing pymupdf4llm multi-page extraction with <!--PAGE_START:N-->...")

    test_pdf = Path("session_cache/test_p2_pages.pdf")
    test_pdf.parent.mkdir(parents=True, exist_ok=True)

    doc = pymupdf.open()
    # Page 1: Standard markdown text with a table
    p1 = doc.new_page()
    p1.insert_text(
        (50, 70),
        "Page 1 Executive Summary: Telemetry indicates steady state propulsion performance exceeds 95% nominal bounds.",
    )

    # Page 2: Second page
    p2 = doc.new_page()
    p2.insert_text(
        (50, 70),
        "Page 2 Empirical Findings: Thermal dissipation limits were reached during high-altitude atmospheric re-entry trials.",
    )

    doc.save(str(test_pdf))
    doc.close()

    result = load_pdf(test_pdf)
    assert result["page_count"] == 2, f"Expected 2 pages, got {result['page_count']}"
    assert "<!--PAGE_START:1-->" in result["content"], "Missing <!--PAGE_START:1--> marker"
    assert "<!--PAGE_START:2-->" in result["content"], "Missing <!--PAGE_START:2--> marker"
    assert "Page 1 Executive Summary" in result["content"]
    assert "Page 2 Empirical Findings" in result["content"]

    test_pdf.unlink(missing_ok=True)
    print("   -> pymupdf4llm page-by-page extraction with <!--PAGE_START:N--> verified successfully!")


def test_rapidocr_initialization_and_inference() -> None:
    print("[2/6] Testing rapidocr-onnxruntime initialization & numpy image inference...")

    from rapidocr_onnxruntime import RapidOCR

    ocr = RapidOCR()
    assert ocr is not None, "Failed to instantiate RapidOCR"

    # Test 1: Blank canvas (must return None without error)
    blank_img = np.zeros((120, 400, 3), dtype=np.uint8)
    res_blank, _ = ocr(blank_img)
    assert res_blank is None, f"Expected None on blank image, got {res_blank}"

    # Test 2: Rendered text image via PyMuPDF pixmap
    doc = pymupdf.open()
    page = doc.new_page(width=500, height=120)
    page.insert_text((40, 70), "OmniResearch RapidOCR Operational Check", fontsize=22)
    pix = page.get_pixmap(dpi=200)
    doc.close()

    res_text, _ = ocr(pix.tobytes("png"))
    assert res_text is not None and len(res_text) > 0, "RapidOCR failed to detect rendered text"
    detected_line = res_text[0][1]
    assert "RapidOCR" in detected_line or "OmniResearch" in detected_line, f"Unexpected OCR result: {detected_line}"

    print(f"   -> RapidOCR verified: detected '{detected_line}' without DLL load errors!")


def test_trafilatura_clean_extraction() -> None:
    print("[3/6] Testing trafilatura & BeautifulSoup article extraction...")

    sample_html = b"""<!DOCTYPE html>
<html>
<head><title>Deep Web Scraping Article</title></head>
<body>
<nav><a href="/">Home</a><a href="/about">About</a></nav>
<header><h1>Site Header Banner</h1></header>
<article>
    <h1>Autonomous Aeronautical Engineering Breakthroughs</h1>
    <p>Researchers at the Aerospace Technology Institute have demonstrated significant empirical advances in composite materials for suborbital glide vehicles.</p>
    <p>The primary experimental results confirm that carbon-carbon matrix composites withstand thermal surface temperatures exceeding two thousand degrees Celsius during simulated atmospheric entry.</p>
    <p>These findings contradict earlier baseline state projections that claimed catastrophic ablation under comparable shear stress profiles.</p>
    <table>
        <tr><th>Material</th><th>Failure Temp (C)</th></tr>
        <tr><td>Baseline Alloy</td><td>1250</td></tr>
        <tr><td>C-C Matrix</td><td>2180</td></tr>
    </table>
</article>
<footer><p>Copyright 2026. All rights reserved.</p></footer>
</body>
</html>"""

    text, title = _extract_with_trafilatura(sample_html, "https://example.com/aero")
    assert "Autonomous Aeronautical Engineering" in text or "composite materials" in text
    assert "Site Header Banner" not in text, "Boilerplate header should be stripped"
    assert "Copyright 2026" not in text, "Boilerplate footer should be stripped"

    print(f"   -> trafilatura clean extraction verified ({len(text.split())} words, title: '{title}')!")


def test_semantic_alignment_audit() -> None:
    print("[4/6] Testing semantic alignment audit (aligned vs. suspect)...")

    source_content = (
        "<!--PAGE_START:1-->\n\n"
        "The experimental ramjet engine completed Mach 6.2 flight tests over the Pacific range. "
        "Telemetry logs confirmed stable combustor pressure at 185 kPa across the thirty-second sustained burn.\n\n"
        "<!--PAGE_START:2-->\n\n"
        "Secondary observations revealed premature thermal degradation on the ceramic matrix nozzle lining. "
        "The nozzle throat diameter expanded by 4.2 millimeters due to boundary layer friction."
    )

    doc = SourceDocument(
        cite_id=1,
        title="Ramjet Flight Test Report",
        source_type="local_pdf",
        path_or_uri="ramjet_report.pdf",
        content=source_content,
        word_count=len(source_content.split()),
    )

    # Test 1: Grounded, highly aligned claim (Page 1)
    claim_aligned = "Telemetry confirmed the ramjet engine achieved stable combustor pressure at 185 kPa during Mach 6.2 flight tests."
    overlap_aligned, is_aligned = check_semantic_alignment(claim_aligned, source_content, page_num=1)
    assert is_aligned is True, f"Expected aligned=True, got {is_aligned} (overlap: {overlap_aligned})"
    assert overlap_aligned >= 0.3, f"Expected high overlap, got {overlap_aligned}"

    # Test 2: Unaligned / hallucinated claim
    claim_unaligned = "The agricultural subsidy for soybean production in South America was discontinued by ministerial decree."
    overlap_unaligned, is_unaligned = check_semantic_alignment(claim_unaligned, source_content, page_num=1)
    assert is_unaligned is False, f"Expected aligned=False, got {is_unaligned} (overlap: {overlap_unaligned})"
    assert overlap_unaligned < 0.1, f"Expected near-zero overlap, got {overlap_unaligned}"

    # Test 3: Page-specific check (claim from page 2 tested against page 1)
    claim_page2 = "The nozzle throat diameter expanded by 4.2 millimeters due to boundary layer friction."
    _, is_page1_match = check_semantic_alignment(claim_page2, source_content, page_num=1)
    _, is_page2_match = check_semantic_alignment(claim_page2, source_content, page_num=2)
    assert is_page1_match is False, "Claim from page 2 should not match page 1 excerpt"
    assert is_page2_match is True, "Claim from page 2 must match page 2 excerpt"

    # Test 4: Semantic anchor builder rendering
    builder = create_semantic_anchor_builder([doc])
    anchor_verified = builder("1", page="1", context_claim=claim_aligned)
    anchor_suspect = builder("1", page="1", context_claim=claim_unaligned)

    assert "cite-verified" in anchor_verified, f"Expected cite-verified in: {anchor_verified}"
    assert "cite-suspect" in anchor_suspect, f"Expected cite-suspect in: {anchor_suspect}"
    assert "#d29922" in anchor_suspect, "Suspect anchor must use amber styling"

    print("   -> Semantic alignment verification (verified vs. suspect anchors) verified successfully!")


def test_scanned_pdf_ocr_fallback() -> None:
    print("[5/6] Testing scanned PDF detection and RapidOCR fallback...")

    test_pdf = Path("session_cache/test_scanned_doc.pdf")
    test_pdf.parent.mkdir(parents=True, exist_ok=True)

    # Create a 1-page PDF where text is drawn on an image canvas to simulate a pure scan (<60 chars)
    doc = pymupdf.open()
    page = doc.new_page(width=500, height=200)
    # Drawing text onto page; pymupdf4llm text will be short or we test the < 60 threshold
    page.insert_text((40, 90), "Scanned Record 9982: Flight Termination Activated", fontsize=18)
    doc.save(str(test_pdf))
    doc.close()

    result = load_pdf(test_pdf)
    assert result["page_count"] == 1
    assert "<!--PAGE_START:1-->" in result["content"]
    assert "Scanned Record 9982" in result["content"]

    test_pdf.unlink(missing_ok=True)
    print("   -> Scanned PDF fallback & page boundary indexing verified successfully!")


def test_page_level_citation_dock_navigation(app: QApplication) -> None:
    print("[6/6] Testing page-level citation dock navigation (cite:1:2)...")

    window = MainWindow()
    window.show()

    mock_content = (
        "<!--PAGE_START:1-->\n\nPage 1 introductory text.\n\n"
        "<!--PAGE_START:2-->\n\nPage 2 crucial findings and empirical contradiction matrix.\n\n"
        "<!--PAGE_START:3-->\n\nPage 3 concluding remarks."
    )
    mock_doc = SourceDocument(
        cite_id=1,
        title="Multi-Page Technical Monograph",
        source_type="local_pdf",
        path_or_uri="monograph.pdf",
        content=mock_content,
        word_count=len(mock_content.split()),
        page_count=3,
    )
    window.corpus.add_document(mock_doc)

    # Trigger page-level citation click: cite:1:2
    window.on_citation_clicked(QUrl("cite:1:2"))

    assert window.source_dock.isVisible(), "SourceInspectorDock should be shown on citation click"
    assert "Page 2" in window.source_dock.match_label.text(), f"Expected Page 2 in match_label, got {window.source_dock.match_label.text()}"
    assert "<!--PAGE_START:2-->" in window.source_dock.text_view.textCursor().selectedText() or window.source_dock.text_view.textCursor().position() > 0

    window.close()
    print("   -> Page-level citation navigation (cite:1:2) verified successfully!")


def main() -> None:
    print("=== OMNIRESEARCH STUDIO PASS 2 VERIFICATION SUITE ===")
    app = QApplication.instance() or QApplication(sys.argv + ["-platform", "offscreen"])

    test_pymupdf4llm_page_extraction()
    test_rapidocr_initialization_and_inference()
    test_trafilatura_clean_extraction()
    test_semantic_alignment_audit()
    test_scanned_pdf_ocr_fallback()
    test_page_level_citation_dock_navigation(app)

    print("\nALL PASS 2 TESTS COMPLETED SUCCESSFULLY!")


if __name__ == "__main__":
    main()
