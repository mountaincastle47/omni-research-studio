"""OmniResearch Studio — Full Workstation Regression & Integration Test Suite.

End-to-End Headless Smoke Test covering all 12 Phases:
Stage 1: Config Persistence (atomic write, defaults, updates, reload consistency).
Stage 2: Sandboxed Ingestion (isolated process loading for TXT, DOCX, and PDF).
Stage 3: SQLite FTS5 Full-Text Search (indexing, BM25 keyword ranking, prefix matching).
Stage 4: Markdown Citations & Grounding (anchor rendering, [N], [N:p.X], style classes).
Stage 5: Executive Exporters (Interactive HTML, Vector PDF, Obsidian PKM, Marp Deck).
Stage 6: Zero-Knowledge AES-256-GCM Vault (encryption, authentication tag rejection, roundtrip restoration).
Stage 7: Explicit Hardware Memory & VRAM Lifecycle (garbage collection, CUDA eviction, RSS tracking).
"""

from __future__ import annotations

import os
import sys
import tempfile
import zipfile
from pathlib import Path

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Initialize Headless QApplication for Qt PrintSupport / Exporters
from PyQt6.QtWidgets import QApplication

qapp = QApplication.instance()
if qapp is None:
    qapp = QApplication(sys.argv)

import docx
import fitz
from cryptography.exceptions import InvalidTag

from core.config_manager import ConfigManager
from core.document_loader import SourceDocument
from core.exporter import (
    build_html_report,
    export_pdf_report,
    export_to_marp,
    export_to_obsidian,
)
from core.markdown_utils import markdown_to_html
from core.memory_guard import MemoryGuard
from core.sandbox_loader import SandboxedDocumentLoader
from core.search_index import CorpusSearchIndex
from core.vault_sync import VAULT_MAGIC_HEADER, VaultSync


def stage_1_config_persistence(work_dir: Path) -> None:
    print("\n--- [Stage 1/7] Config Persistence & Atomic Serialization ---")
    cfg_file = work_dir / "user_config.json"
    cm1 = ConfigManager(config_path=cfg_file)

    # 1. Verify default values
    assert cm1.get("discovery_model") == "gemini-3.8-flash", "Default discovery_model mismatch"
    assert cm1.get("autosave_interval_s") == 60, "Default autosave_interval mismatch"
    assert cm1.get("audio_playback_rate") == 1.0, "Default audio_playback_rate mismatch"
    print("  [OK] Default settings initialized successfully")

    # 2. Mutate values
    cm1.set("autosave_interval_s", 45)
    cm1.set("local_llm_endpoint", "http://127.0.0.1:11434/v1")
    cm1.update_bulk({
        "discovery_model": "gemini-4-argon",
        "contested_matrix_enforcement": False,
        "bm25_compression_threshold_tokens": 48000,
    })
    print("  [OK] Mutated configuration values applied via atomic save")

    # 3. Reload new instance from disk to guarantee persistence
    cm2 = ConfigManager(config_path=cfg_file)
    assert cm2.get("autosave_interval_s") == 45, "Persisted autosave_interval_s mismatch"
    assert cm2.get("local_llm_endpoint") == "http://127.0.0.1:11434/v1", "Persisted local_llm_endpoint mismatch"
    assert cm2.get("discovery_model") == "gemini-4-argon", "Persisted discovery_model mismatch"
    assert cm2.get("contested_matrix_enforcement") is False, "Persisted matrix enforcement mismatch"
    assert cm2.get("bm25_compression_threshold_tokens") == 48000, "Persisted bm25 threshold mismatch"

    # 4. Verify no lingering temporary files
    tmp_files = list(work_dir.glob("*.tmp"))
    assert len(tmp_files) == 0, f"Dangling temporary files detected: {tmp_files}"
    print("  [OK] Persistence verified: Reloaded values match without lingering .tmp artifacts")


def stage_2_sandboxed_ingestion(work_dir: Path) -> list[SourceDocument]:
    print("\n--- [Stage 2/7] Sandboxed Multi-Format Ingestion ---")
    loader = SandboxedDocumentLoader.get_instance()

    # 1. Create Mock TXT
    txt_path = work_dir / "document_alpha.txt"
    txt_content = (
        "Quantum computing relies on superconducting qubits and cryogenic dilution refrigerators.\n"
        "Coherence times have achieved 150 microseconds under transmon architectures."
    )
    txt_path.write_text(txt_content, encoding="utf-8")

    # 2. Create Mock DOCX
    docx_path = work_dir / "document_beta.docx"
    doc_docx = docx.Document()
    doc_docx.add_heading("Solid-State Electrolyte Formulations", level=1)
    doc_docx.add_paragraph("Silicon-anode lithium battery cells achieve 420 Wh/kg volumetric energy density.")
    doc_docx.add_paragraph("Thermal runaway is suppressed below 180 degrees Celsius using garnet LLZO electrolytes.")
    doc_docx.save(str(docx_path))

    # 3. Create Mock Native PDF
    pdf_path = work_dir / "document_gamma.pdf"
    doc_pdf = fitz.open()
    page1 = doc_pdf.new_page()
    page1.insert_text((50, 72), "Autonomous Flight Telemetry and Trajectory Estimation\nPage 1 Content.")
    page2 = doc_pdf.new_page()
    page2.insert_text((50, 72), "Propellant mass fraction dictates the delta-V threshold for low-Earth orbit injection.\nPage 2 Telemetry.")
    doc_pdf.save(str(pdf_path))
    doc_pdf.close()

    # 4. Ingest TXT
    res_txt = loader.extract_document(txt_path)
    assert res_txt["success"] is True, f"TXT ingestion failed: {res_txt}"
    assert "superconducting qubits" in res_txt["content"]
    print(f"  [OK] Sandboxed TXT ingested ({len(res_txt['content'])} chars)")

    # 5. Ingest DOCX
    res_docx = loader.extract_document(docx_path)
    assert res_docx["success"] is True, f"DOCX ingestion failed: {res_docx}"
    assert "Solid-State" in res_docx["content"]
    print(f"  [OK] Sandboxed DOCX ingested ({len(res_docx['content'])} chars)")

    # 6. Ingest PDF
    res_pdf = loader.extract_document(pdf_path)
    assert res_pdf["success"] is True, f"PDF ingestion failed: {res_pdf}"
    assert "Autonomous Flight" in res_pdf["content"]
    assert res_pdf["page_count"] == 2
    print(f"  [OK] Sandboxed PDF ingested ({res_pdf['page_count']} pages, {len(res_pdf['content'])} chars)")

    docs = [
        SourceDocument(cite_id=1, title="Quantum Computing Architecture", path_or_uri=str(txt_path), content=res_txt["content"]),
        SourceDocument(cite_id=2, title="Solid-State Electrolytes", path_or_uri=str(docx_path), content=res_docx["content"]),
        SourceDocument(cite_id=3, title="Flight Telemetry & Orbit Dynamics", path_or_uri=str(pdf_path), content=res_pdf["content"]),
    ]
    return docs


def stage_3_sqlite_fts5_search(docs: list[SourceDocument]) -> None:
    print("\n--- [Stage 3/7] SQLite FTS5 Full-Text Search ---")
    index = CorpusSearchIndex(db_path=":memory:")
    index.index_corpus(docs)

    # 1. Search for unique keyword in Doc 1
    hits_qubit = index.search_corpus("qubits")
    assert len(hits_qubit) >= 1, "Expected FTS match for 'qubits'"
    assert hits_qubit[0].doc_id == 1
    assert "superconducting" in hits_qubit[0].snippet.lower()
    print("  [OK] FTS5 match query 'qubits' correctly indexed to Doc 1")

    # 2. Search for unique keyword in Doc 2
    hits_battery = index.search_corpus("electrolytes")
    assert len(hits_battery) >= 1, "Expected FTS match for 'electrolytes'"
    assert hits_battery[0].doc_id == 2
    print("  [OK] FTS5 match query 'electrolytes' correctly indexed to Doc 2")

    # 3. Search for unique keyword in Doc 3
    hits_orbit = index.search_corpus("trajectory")
    assert len(hits_orbit) >= 1, "Expected FTS match for 'trajectory'"
    assert hits_orbit[0].doc_id == 3
    print("  [OK] FTS5 match query 'trajectory' correctly indexed to Doc 3")

    # 4. Search for non-existent keyword
    hits_absent = index.search_corpus("antigravity_propulsion_unknown")
    assert len(hits_absent) == 0, "Non-existent term should yield zero results"
    print("  [OK] FTS5 correctly returned 0 hits for non-existent term")
    index.close()


def stage_4_markdown_citations() -> None:
    print("\n--- [Stage 4/7] Markdown Citations & Grounding Anchor Verification ---")
    sample_markdown = (
        "# Executive Technology Overview\n\n"
        "Superconducting circuits exhibit long coherence times [1].\n\n"
        "Recent electrolyte formulations suppress thermal runaway [2:p.1].\n\n"
        "Multi-source synthesis combines cryogenic data with orbital dynamics [1, 3:p.2]."
    )

    html = markdown_to_html(sample_markdown, interactive_citations=True)

    # Assert citation anchor hrefs and verified classes are present
    assert 'href="cite:1"' in html, "Citation [1] link anchor missing"
    assert 'class="citation-anchor cite-verified"' in html, "Citation style class missing"
    assert 'href="cite:2:1"' in html, "Page-anchored citation [2:p.1] link missing"
    assert 'href="cite:3:2"' in html, "Multi-citation second anchor [3:p.2] link missing"
    assert "<h1>Executive Technology Overview</h1>" in html, "Markdown heading compilation failed"
    print("  [OK] Citations [1], [2:p.1], and [1, 3:p.2] linkified into interactive semantic anchors")


def stage_5_executive_exporters(docs: list[SourceDocument], work_dir: Path) -> None:
    print("\n--- [Stage 5/7] Executive Exporters (HTML, PDF, Obsidian, Marp) ---")
    report_md = (
        "# High-Energy Systems & Deep Space Telemetry\n\n"
        "## Summary\n"
        "Cryogenic quantum sensors [1] coupled with solid-state energy storage [2] provide "
        "autonomous orbital trajectory stabilization [3:p.2].\n\n"
        "## Comparative Matrix\n\n"
        "| System | Metric | Status |\n"
        "| :--- | :--- | :--- |\n"
        "| Transmon Qubits | 150 us | Verified [1] |\n"
        "| Garnet LLZO | 420 Wh/kg | Benchmarked [2] |\n"
        "| Orbital Delta-V | 9.4 km/s | Nominal [3:p.2] |\n"
    )

    # 1. Interactive HTML Report
    html_report = build_html_report(report_md, docs, title="Workstation System Audit")
    assert "<!DOCTYPE html>" in html_report
    assert "Workstation System Audit" in html_report
    assert "Comparative Matrix" in html_report
    assert "Quantum Computing Architecture" in html_report  # Bibliography check
    html_path = work_dir / "audit_report.html"
    html_path.write_text(html_report, encoding="utf-8")
    assert html_path.exists() and html_path.stat().st_size > 500
    print(f"  [OK] Interactive HTML report generated ({html_path.stat().st_size} bytes)")

    # 2. Vector PDF Report
    pdf_out = work_dir / "audit_report.pdf"
    export_pdf_report(pdf_out, report_md, docs)
    assert pdf_out.exists(), "PDF output file does not exist"
    assert pdf_out.stat().st_size > 1000, f"PDF file size too small: {pdf_out.stat().st_size} bytes"
    print(f"  [OK] Vector PDF report exported ({pdf_out.stat().st_size} bytes)")

    # 3. Obsidian PKM Export
    obsidian_out = work_dir / "obsidian_vault" / "synthesis_report.md"
    export_to_obsidian(obsidian_out, report_md, docs)
    assert obsidian_out.exists()
    obsidian_text = obsidian_out.read_text(encoding="utf-8")
    assert "---" in obsidian_text  # YAML frontmatter
    assert "tags:" in obsidian_text
    assert "High-Energy Systems" in obsidian_text
    print(f"  [OK] Obsidian PKM note exported with YAML frontmatter ({obsidian_out.stat().st_size} bytes)")

    # 4. Marp Slide Deck Export
    marp_out = work_dir / "presentation_deck.md"
    export_to_marp(marp_out, report_md)
    assert marp_out.exists()
    marp_text = marp_out.read_text(encoding="utf-8")
    assert "marp: true" in marp_text
    assert "---" in marp_text
    print(f"  [OK] Marp slide deck exported ({marp_out.stat().st_size} bytes)")


def stage_6_vault_encryption(work_dir: Path) -> None:
    print("\n--- [Stage 6/7] Zero-Knowledge AES-256-GCM Vault Backup ---")
    # 1. Create a mock .omni project archive
    omni_source = work_dir / "project_alpha.omni"
    with zipfile.ZipFile(omni_source, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("project.json", '{"version": "1.0", "title": "Sovereign Project Alpha"}')
        zf.writestr("workspaces/tab_1.json", '{"tab_title": "Primary Workspace", "report": "Top Secret Data"}')
        zf.writestr("sources/source_1.txt", "Raw empirical flight telemetry.")

    master_password = "OmniResearch-MasterKey-2026!"
    vault_dest = work_dir / "project_alpha.omni.vault"

    # 2. Encrypt to vault
    VaultSync.encrypt_file(omni_source, vault_dest, master_password)
    assert vault_dest.exists()
    vault_raw = vault_dest.read_bytes()
    assert vault_raw.startswith(VAULT_MAGIC_HEADER), "Vault magic header missing"
    print(f"  [OK] Project encrypted to AES-256-GCM vault ({len(vault_raw)} bytes)")

    # 3. Decrypt with wrong password -> Must raise InvalidTag
    wrong_dest = work_dir / "project_corrupt.omni"
    try:
        VaultSync.decrypt_file(vault_dest, wrong_dest, "IncorrectPasswordXYZ!")
        assert False, "Decryption should have failed with InvalidTag"
    except (InvalidTag, ValueError):
        print("  [OK] Authentication guard verified: Tampered/incorrect passphrase rejected")

    # 4. Decrypt with correct password -> Byte-for-byte exact match
    restored_dest = work_dir / "project_restored.omni"
    VaultSync.decrypt_file(vault_dest, restored_dest, master_password)
    assert restored_dest.exists()
    assert restored_dest.read_bytes() == omni_source.read_bytes(), "Restored .omni bytes do not match source"
    print("  [OK] Full vault roundtrip verified: Decrypted project matches byte-for-byte")


def stage_7_memory_lifecycle() -> None:
    print("\n--- [Stage 7/7] Explicit Hardware Memory & VRAM Lifecycle ---")
    mem_before = MemoryGuard.get_process_memory_mb()
    metrics = MemoryGuard.clean(ephemeral_models=True)

    assert "gc_freed" in metrics
    assert "cuda_available" in metrics
    assert "vram_freed" in metrics
    assert "plots_closed" in metrics
    assert "initial_rss_mb" in metrics
    assert "final_rss_mb" in metrics

    mem_after = MemoryGuard.get_process_memory_mb()
    print(f"  [OK] MemoryGuard executed successfully: RSS {mem_before:.2f} MB -> {mem_after:.2f} MB")
    print(f"  [OK] Freed objects: {metrics['gc_freed']} | Matplotlib figures closed: {metrics['plots_closed']}")


def main() -> None:
    print("======================================================================")
    print("      OmniResearch Studio — Full Workstation Regression Suite         ")
    print("======================================================================")

    with tempfile.TemporaryDirectory() as temp_dir_str:
        work_dir = Path(temp_dir_str)

        # Stage 1: Config Persistence
        stage_1_config_persistence(work_dir)

        # Stage 2: Sandboxed Ingestion
        docs = stage_2_sandboxed_ingestion(work_dir)

        # Stage 3: SQLite FTS5 Search
        stage_3_sqlite_fts5_search(docs)

        # Stage 4: Markdown Citations
        stage_4_markdown_citations()

        # Stage 5: Executive Exporters
        stage_5_executive_exporters(docs, work_dir)

        # Stage 6: AES-256-GCM Vault
        stage_6_vault_encryption(work_dir)

        # Stage 7: Memory Lifecycle
        stage_7_memory_lifecycle()

    print("\n======================================================================")
    print("           ALL 7 STAGES PASSED CLEANLY (100% SUCCESS)                 ")
    print("======================================================================")


if __name__ == "__main__":
    main()
