import os
import datetime
import logging
from pipeline.deduplicate import load_seen_ids, save_seen_ids

CLAUDE_FILE = "CLAUDE.md"

logger = logging.getLogger(__name__)


def update_memory(posts: list[dict], run_metrics: dict) -> None:
    """Persists state after a successful run."""
    # Part A: Update seen IDs
    current_ids = load_seen_ids()
    new_ids = current_ids + [p["id"] for p in posts]
    save_seen_ids(new_ids)

    # Part B & C: Update CLAUDE.md
    try:
        if not os.path.exists(CLAUDE_FILE):
            _create_initial_claude()

        with open(CLAUDE_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()

        new_lines = []
        skip_to_history = False

        # We rewrite the "Last Run" section and update history
        # Find the ## Last Run section
        last_run_start = -1
        history_start = -1

        for i, line in enumerate(lines):
            if line.startswith("## Last Run"):
                last_run_start = i
            elif line.startswith("## Run History"):
                history_start = i

        # Construct header and configuration part
        if last_run_start != -1:
            new_lines = lines[:last_run_start]
        else:
            # Fallback if file is weird
            _create_initial_claude()
            with open(CLAUDE_FILE, "r", encoding="utf-8") as f:
                new_lines = f.readlines()[:12]  # Up to before Last Run

        # Add updated Last Run
        new_lines.append("## Last Run\n")
        new_lines.append(f"- Date: {run_metrics.get('date')}\n")
        new_lines.append(f"- Posts fetched: {run_metrics.get('posts_fetched')}\n")
        new_lines.append(
            f"- Posts after dedup: {run_metrics.get('posts_after_dedup')}\n"
        )
        new_lines.append(
            f"- Posts after filter: {run_metrics.get('posts_after_filter')}\n"
        )
        new_lines.append(f"- Posts in digest: {run_metrics.get('posts_in_digest')}\n")
        new_lines.append(
            f"- Comments fetched: {run_metrics.get('comments_success')}/{run_metrics.get('comments_total')}\n"
        )
        new_lines.append(
            f"- Degraded mode: {'yes' if run_metrics.get('degraded') else 'no'}\n"
        )
        new_lines.append(f"- Runtime: {run_metrics.get('runtime')}s\n")
        new_lines.append(f"- Status: {run_metrics.get('status')}\n\n")

        # Add Run History
        new_lines.append("## Run History\n")
        history_entries = []
        if history_start != -1:
            # Extract existing history entries
            for line in lines[history_start + 1 :]:
                if line.strip().startswith("- "):
                    history_entries.append(line)
                elif line.startswith("##"):  # Another section or empty
                    break

        # Add new entry at the top
        date_short = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        new_entry = f"- {date_short} | {run_metrics.get('posts_in_digest')} posts | {run_metrics.get('runtime')}s | {run_metrics.get('status')}\n"
        history_entries.insert(0, new_entry)

        # Keep only last 30
        history_entries = history_entries[:30]
        new_lines.extend(history_entries)

        with open(CLAUDE_FILE, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

        logger.info(f"Updated memory in {CLAUDE_FILE}")

    except Exception as e:
        logger.error(f"Failed to update CLAUDE.md memory: {e}")


def _create_initial_claude():
    """Initializes CLAUDE.md if missing."""
    content = """# The TV Signal — Project Memory

## Project
Agentic RSS digest system for /r/television.

## Configuration
- Subreddit: television
- Min comments: 50
- Max seen IDs: 200
- Schedule: Daily 11 PM EST

## Last Run
No runs yet.

## Run History
No runs yet.
"""
    with open(CLAUDE_FILE, "w", encoding="utf-8") as f:
        f.write(content)
