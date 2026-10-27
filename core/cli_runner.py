"""Unattended Batch Research CLI Engine:
Executes unattended headless research pipelines over batches of topics,
generating grounded synthesis reports, audio briefings, executive PDFs, and .omni packages.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional

# Ensure offscreen Qt platform for headless document exporting
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from core.audio_studio import AudioStudioGenerator, NeuralVoiceSynthesizer, PodcastScript
from core.config import ConfigManager, DEFAULT_SYNTHESIS_MODEL
from core.document_loader import DocumentCorpus, SourceDocument
from core.exporter import build_html_report, export_pdf_report
from core.notebook_synthesis import NotebookSynthesizer
from core.project_manager import ProjectState, WorkspaceTabState, save_project


def emit_log(topic: str, status: str, progress: float = 0.0, extra: Optional[Dict[str, Any]] = None) -> None:
    """Output continuous JSON-lines log to stdout for monitoring agents/scripts."""
    payload = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "topic": topic,
        "status": status,
        "progress": round(progress, 3),
    }
    if extra:
        payload.update(extra)
    print(json.dumps(payload, ensure_ascii=False), flush=True)


class BatchResearchRunner:
    """Executes unattended end-to-end research pipelines."""

    def __init__(
        self,
        config_manager: Optional[ConfigManager] = None,
        model_name: str = DEFAULT_SYNTHESIS_MODEL,
        render_audio: bool = False,
        export_all: bool = True,
    ) -> None:
        self.config_manager = config_manager or ConfigManager()
        self.model_name = model_name
        self.render_audio = render_audio
        self.export_all = export_all

    def process_topic(self, topic: str, out_dir: Path) -> Dict[str, Any]:
        """Execute full pipeline for a single topic."""
        safe_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in topic)[:50]
        topic_dir = out_dir / safe_name
        topic_dir.mkdir(parents=True, exist_ok=True)

        emit_log(topic, "INITIATING_RESEARCH", progress=0.05)

        # 1. Corpus setup & initial primary source extraction
        corpus = DocumentCorpus()
        # Seed synthesis with topic overview seed
        seed_doc = SourceDocument(
            cite_id=1,
            title=f"Initial Ingestion: {topic}",
            source_type="file",
            path_or_uri=str(topic_dir / "seed.txt"),
            content=f"Primary research inquiry for: {topic}. Requires forensic technical evaluation and empirical telemetry.",
        )
        corpus.add_document(seed_doc)

        emit_log(topic, "SYNTHESIZING_REPORT", progress=0.30)
        client = None
        api_key = self.config_manager.get_api_key()
        if api_key:
            try:
                from google import genai
                client = genai.Client(api_key=api_key)
            except Exception:
                client = None
        synthesizer = NotebookSynthesizer(client=client, model_name=self.model_name)

        # Execute Grounded Synthesis
        synth_result = synthesizer.synthesize(
            query=topic,
            documents=corpus.get_all_documents(),
        )
        report_md = synth_result.markdown_report

        # Save Markdown Report
        report_path = topic_dir / f"{safe_name}_report.md"
        report_path.write_text(report_md, encoding="utf-8")

        # 2. Executive Exports (HTML & PDF)
        html_path = None
        pdf_path = None
        if self.export_all:
            emit_log(topic, "EXPORTING_DOCUMENTS", progress=0.60)
            html_content = build_html_report(
                markdown_text=report_md,
                documents=corpus.get_all_documents(),
                title=f"Executive Report: {topic}",
            )
            html_path = topic_dir / f"{safe_name}_report.html"
            html_path.write_text(html_content, encoding="utf-8")

            # Vector PDF
            try:
                pdf_target = topic_dir / f"{safe_name}_report.pdf"
                export_pdf_report(
                    markdown_text=report_md,
                    documents=corpus.get_all_documents(),
                    output_path=pdf_target,
                )
                pdf_path = pdf_target
            except Exception as pdf_err:
                emit_log(topic, "PDF_EXPORT_WARNING", progress=0.70, extra={"error": str(pdf_err)})

        # 3. Audio Briefing (if requested)
        audio_path = None
        if self.render_audio:
            emit_log(topic, "SYNTHESIZING_AUDIO", progress=0.75)
            try:
                api_key = self.config_manager.get_api_key()
                if api_key:
                    from google import genai
                    client = genai.Client(api_key=api_key)
                    generator = AudioStudioGenerator(client=client, model_name=self.model_name)
                    script = generator.generate_podcast_script(
                        report_markdown=report_md,
                        user_focus=f"Executive 2-minute dialogue overview on {topic}",
                    )
                    audio_target = topic_dir / f"{safe_name}_briefing.mp3"
                    synth = NeuralVoiceSynthesizer()
                    synth.synthesize_dialogue(script, output_path=str(audio_target))
                    audio_path = audio_target
            except Exception as audio_err:
                emit_log(topic, "AUDIO_SYNTHESIS_WARNING", progress=0.85, extra={"error": str(audio_err)})

        # 4. Project State Packaging (.omni)
        emit_log(topic, "PACKAGING_PROJECT", progress=0.90)
        workspace = WorkspaceTabState(
            tab_id=f"ws_{int(time.time())}",
            title=topic[:30],
            topic=topic,
            query=topic,
            synthesis_original=report_md,
            audio_mp3_path=str(audio_path) if audio_path else None,
        )
        project_state = ProjectState(
            title=topic,
            workspaces=[workspace],
            documents=corpus.get_all_documents(),
        )
        omni_file = topic_dir / f"{safe_name}.omni"
        save_project(project_state, omni_file)

        emit_log(topic, "COMPLETED", progress=1.0, extra={
            "report_path": str(report_path),
            "html_path": str(html_path) if html_path else None,
            "pdf_path": str(pdf_path) if pdf_path else None,
            "omni_path": str(omni_file),
            "audio_path": str(audio_path) if audio_path else None,
        })

        return {
            "topic": topic,
            "out_dir": str(topic_dir),
            "report_md": str(report_path),
            "omni_file": str(omni_file),
            "pdf_file": str(pdf_path) if pdf_path else None,
        }

    def run_batch(self, topics: List[str], out_dir: Path) -> List[Dict[str, Any]]:
        """Sequentially process a batch of topics."""
        results = []
        total = len(topics)
        out_dir.mkdir(parents=True, exist_ok=True)

        emit_log("BATCH", f"Starting batch processing of {total} topic(s)", progress=0.0)
        for i, t in enumerate(topics, 1):
            emit_log(t, f"Processing topic {i}/{total}", progress=(i - 1) / total)
            try:
                res = self.process_topic(t, out_dir)
                results.append(res)
            except Exception as exc:
                emit_log(t, "FAILED", progress=i / total, extra={"error": str(exc)})
        emit_log("BATCH", "Batch execution complete.", progress=1.0)
        return results


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="OmniResearch Studio Unattended Batch Research CLI")
    parser.add_argument("--batch", type=str, help="Path to JSON file containing array of topics")
    parser.add_argument("--topic", type=str, help="Single topic string to process")
    parser.add_argument("--out-dir", type=str, default="./research_batch", help="Output directory")
    parser.add_argument("--export-all", action="store_true", default=True, help="Export HTML, Vector PDF, and BibTeX")
    parser.add_argument("--render-audio", action="store_true", default=False, help="Synthesize edge-tts neural audio briefing")
    parser.add_argument("--model", type=str, default=DEFAULT_SYNTHESIS_MODEL, help="Gemini or local model name")

    args = parser.parse_args(argv)

    topics: List[str] = []
    if args.batch:
        batch_path = Path(args.batch)
        if not batch_path.exists():
            print(f"Error: Batch JSON file not found: {batch_path}", file=sys.stderr)
            return 1
        raw_data = json.loads(batch_path.read_text(encoding="utf-8"))
        if isinstance(raw_data, list):
            for item in raw_data:
                if isinstance(item, str):
                    topics.append(item)
                elif isinstance(item, dict) and "topic" in item:
                    topics.append(item["topic"])
    elif args.topic:
        topics.append(args.topic)
    else:
        print("Error: Either --batch <file.json> or --topic '<topic>' must be specified.", file=sys.stderr)
        parser.print_help()
        return 1

    runner = BatchResearchRunner(
        model_name=args.model,
        render_audio=args.render_audio,
        export_all=args.export_all,
    )
    runner.run_batch(topics, Path(args.out_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
