import json
import os
import logging

SEEN_IDS_FILE = "data/seen_ids.json"
MAX_SEEN_IDS = 200

logger = logging.getLogger(__name__)


def load_seen_ids() -> list[str]:
    """Loads seen IDs from disk. Returns empty list if file doesn't exist or is corrupted."""
    if not os.path.exists(SEEN_IDS_FILE):
        return []

    try:
        with open(SEEN_IDS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            else:
                logger.warning(
                    f"Corrupted seen IDs file: expected list, got {type(data)}"
                )
                return []
    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"Error loading seen IDs: {e}")
        return []


def save_seen_ids(ids: list[str]) -> None:
    """Saves seen IDs to disk, maintaining a rolling window of MAX_SEEN_IDS."""
    if len(ids) > MAX_SEEN_IDS:
        ids = ids[-MAX_SEEN_IDS:]

    try:
        os.makedirs(os.path.dirname(SEEN_IDS_FILE), exist_ok=True)
        with open(SEEN_IDS_FILE, "w", encoding="utf-8") as f:
            json.dump(ids, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save seen IDs: {e}")


def deduplicate(posts: list[dict]) -> list[dict]:
    """Removes posts that have already been seen."""
    seen_ids = set(load_seen_ids())
    original_count = len(posts)

    filtered_posts = [p for p in posts if p["id"] not in seen_ids]
    removed_count = original_count - len(filtered_posts)

    logger.info(
        f"Deduplication: {original_count} -> {len(filtered_posts)} posts ({removed_count} removed)"
    )

    return filtered_posts
