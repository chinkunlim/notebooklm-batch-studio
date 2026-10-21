"""Phase 1A Technical Spike: Verify NotebookLM API & Playwright integration.

Tests NotebookLM authentication, source uploading, single-source selection,
and generation of quizzes, flashcards, mind maps, study guides, and audio.
Results are documented to update ADR-001 with empirical measurements.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

from notebooklm import NotebookLMClient
from notebooklm.paths import get_storage_path

from notebooklm_batch_studio.config.logging_setup import setup_logging
from notebooklm_batch_studio.config.settings import AppConfig

logger = logging.getLogger(__name__)


def check_auth_status(config: AppConfig) -> bool:
    """Check whether a valid authentication storage file exists.

    Args:
        config: The application configuration.

    Returns:
        True if storage_state.json exists and is readable, False otherwise.
    """
    os.environ["NOTEBOOKLM_HOME"] = str(config.notebooklm_home)
    storage_path = get_storage_path()
    if storage_path.exists() and storage_path.stat().st_size > 0:
        logger.info("Found auth storage at %s", storage_path)
        return True
    logger.warning("No auth storage found at %s", storage_path)
    return False


async def run_spike_pipeline(config: AppConfig, include_audio: bool = False) -> dict[str, Any]:
    """Execute the end-to-end NotebookLM technical feasibility spike.

    Args:
        config: Application configuration.
        include_audio: Whether to generate an Audio Overview (consumes daily quota).

    Returns:
        A dictionary summarizing the test results and metrics.

    Raises:
        RuntimeError: If authentication storage is missing.
    """
    os.environ["NOTEBOOKLM_HOME"] = str(config.notebooklm_home)
    storage_path = get_storage_path()
    if not storage_path.exists():
        raise RuntimeError(
            f"Authentication missing at {storage_path}. "
            "Please run 'notebooklm login' or 'python3 scripts/spike_notebooklm.py login' first."
        )

    results: dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "single_source_selection": False,
        "quiz": {"status": "skipped", "questions_count": 0, "duration_s": 0.0},
        "flashcards": {"status": "skipped", "cards_count": 0, "duration_s": 0.0},
        "mind_map": {"status": "skipped", "nodes_count": 0, "duration_s": 0.0},
        "study_guide": {"status": "skipped", "duration_s": 0.0},
        "audio": {"status": "skipped", "duration_s": 0.0, "file_path": None},
        "renaming": {"status": "skipped"},
    }

    test_pdf_path = config.input_dir / "sample_cell_biology.pdf"
    if not test_pdf_path.exists():
        raise FileNotFoundError(f"Sample PDF not found at {test_pdf_path}. Run generate_sample_pdf.py first.")

    output_test_dir = config.output_dir / "spike_test"
    output_test_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Connecting to NotebookLM client from storage: %s", storage_path)
    async with NotebookLMClient.from_storage(path=str(storage_path)) as client:
        # Step 1: Create a temporary test notebook
        nb_name = f"[Spike] Cell Biology {int(time.time())}"
        logger.info("Creating test notebook: %s", nb_name)
        nb = await client.notebooks.create(nb_name)
        nb_id = nb.id
        logger.info("Created notebook ID: %s", nb_id)

        try:
            # Step 2: Upload sample PDF
            logger.info("Uploading sample PDF: %s", test_pdf_path)
            t0 = time.time()
            source = await client.sources.add_file(nb_id, test_pdf_path)
            source_id = source.id
            logger.info("Source uploaded: ID=%s in %.2fs", source_id, time.time() - t0)

            # Wait until ready
            logger.info("Waiting for source processing...")
            await client.sources.wait_until_ready(nb_id, source_id)
            logger.info("Source is ready for artifact generation.")

            # Step 3: Test Single-Source Selection on Quiz Generation
            logger.info("Testing Quiz generation with single source_id: %s", source_id)
            t_quiz = time.time()
            quiz_status = await client.artifacts.generate_quiz(
                notebook_id=nb_id,
                source_ids=[source_id],
                instructions="Generate rigorous multiple choice questions for cell membrane transport.",
            )
            logger.info("Quiz task submitted: %s, waiting for completion...", quiz_status)
            await client.artifacts.wait_for_completion(nb_id, quiz_status.task_id)
            quiz_duration = time.time() - t_quiz

            # Download quiz to JSON
            quiz_file = output_test_dir / "spike_quiz.json"
            await client.artifacts.download_quiz(nb_id, str(quiz_file))
            with open(quiz_file, "r", encoding="utf-8") as qf:
                quiz_data = json.load(qf)

            q_count = len(quiz_data) if isinstance(quiz_data, list) else len(quiz_data.get("questions", []))
            results["single_source_selection"] = True
            results["quiz"] = {
                "status": "success",
                "questions_count": q_count,
                "duration_s": round(quiz_duration, 2),
                "file": str(quiz_file),
            }
            logger.info("Quiz generated with %d questions in %.2fs", q_count, quiz_duration)

            # Step 4: Test Flashcards Generation
            logger.info("Testing Flashcards generation with source_id: %s", source_id)
            t_fc = time.time()
            fc_status = await client.artifacts.generate_flashcards(
                notebook_id=nb_id,
                source_ids=[source_id],
                instructions="Extract vocabulary and core biochemical definitions.",
            )
            await client.artifacts.wait_for_completion(nb_id, fc_status.task_id)
            fc_duration = time.time() - t_fc

            fc_file = output_test_dir / "spike_flashcards.json"
            await client.artifacts.download_flashcards(nb_id, str(fc_file))
            with open(fc_file, "r", encoding="utf-8") as ff:
                fc_data = json.load(ff)

            cards_count = len(fc_data) if isinstance(fc_data, list) else len(fc_data.get("cards", []))
            results["flashcards"] = {
                "status": "success",
                "cards_count": cards_count,
                "duration_s": round(fc_duration, 2),
                "file": str(fc_file),
            }
            logger.info("Flashcards generated with %d cards in %.2fs", cards_count, fc_duration)

            # Step 5: Test Mind Map Generation
            logger.info("Testing Mind Map generation with source_id: %s", source_id)
            t_mm = time.time()
            await client.artifacts.generate_mind_map(
                notebook_id=nb_id,
                source_ids=[source_id],
                instructions="Create a detailed hierarchical breakdown of passive and active transport.",
            )
            mm_duration = time.time() - t_mm
            mm_file = output_test_dir / "spike_mindmap.json"
            await client.artifacts.download_mind_map(nb_id, str(mm_file))

            results["mind_map"] = {
                "status": "success",
                "duration_s": round(mm_duration, 2),
                "file": str(mm_file),
            }
            logger.info("Mind map generated and downloaded in %.2fs", mm_duration)

            # Step 6: Test Renaming Artifact inside NotebookLM
            try:
                quizzes = await client.artifacts.list_quizzes(nb_id)
                if quizzes:
                    target_quiz_id = quizzes[0].id
                    await client.artifacts.rename(nb_id, target_quiz_id, "[03] Quiz 1-基礎")
                    results["renaming"] = {"status": "success", "note": "Renamed quiz artifact in NotebookLM"}
                    logger.info("Artifact renamed successfully to '[03] Quiz 1-基礎'")
                else:
                    results["renaming"] = {"status": "skipped", "note": "No quizzes found to rename"}
            except Exception as rename_err:
                results["renaming"] = {"status": "unsupported_or_failed", "error": str(rename_err)}
                logger.warning("Artifact renaming not supported or failed: %s", rename_err)

            # Step 7: Test Audio Overview (Optional)
            if include_audio:
                logger.info("Testing Audio Overview generation with source_id: %s (Deep Dive)", source_id)
                t_audio = time.time()
                audio_status = await client.artifacts.generate_audio(
                    notebook_id=nb_id,
                    source_ids=[source_id],
                    instructions="Discuss the differences between passive and active transport in detail.",
                )
                await client.artifacts.wait_for_completion(nb_id, audio_status.task_id)
                audio_duration = time.time() - t_audio
                audio_file = output_test_dir / "spike_audio.mp3"
                await client.artifacts.download_audio(nb_id, str(audio_file))
                results["audio"] = {
                    "status": "success",
                    "duration_s": round(audio_duration, 2),
                    "file_path": str(audio_file),
                }
                logger.info("Audio overview generated and downloaded in %.2fs", audio_duration)

        finally:
            # Clean up the spike test notebook
            logger.info("Spike test complete. Retaining or cleaning up notebook %s...", nb_id)
            # Notebooks can be cleaned up if desired: await client.notebooks.delete(nb_id)

    return results


def main() -> None:
    """CLI entrypoint for running the NotebookLM spike."""
    parser = argparse.ArgumentParser(description="NotebookLM Batch Studio - Technical Spike")
    parser.add_argument("command", choices=["check", "login", "run"], help="Action to execute")
    parser.add_argument("--include-audio", action="store_true", help="Generate 1 Audio overview during run")
    args = parser.parse_args()

    config = AppConfig()
    setup_logging(level="INFO", log_dir=None)

    if args.command == "check":
        is_ready = check_auth_status(config)
        if is_ready:
            print(f"✅ Authentication is ready: {get_storage_path()}")
            sys.exit(0)
        else:
            print(f"❌ Not logged in. Storage path: {get_storage_path()}")
            print("Run 'python3 scripts/spike_notebooklm.py login' to log in.")
            sys.exit(1)

    elif args.command == "login":
        print(f"Starting browser login. Credentials will be saved to: {config.notebooklm_home}")
        os.environ["NOTEBOOKLM_HOME"] = str(config.notebooklm_home)
        cmd = f"uv run notebooklm login --storage {get_storage_path()}"
        os.system(cmd)

    elif args.command == "run":
        if not check_auth_status(config):
            print("Authentication missing. Please run login first:")
            print("  python3 scripts/spike_notebooklm.py login")
            sys.exit(1)

        print("Starting Technical Spike pipeline...")
        results = asyncio.run(run_spike_pipeline(config, include_audio=args.include_audio))
        print("\n=== SPIKE RESULTS SUMMARY ===")
        print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
