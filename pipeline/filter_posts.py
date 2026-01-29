import requests
import json
import time
import os
import datetime
import logging
import re

ARTIFACT_DIR = "data/artifacts"
USER_AGENT = "TheTV Signal/1.0 (RSS digest bot)"

# Filter Constants
MIN_COMMENTS = 50
EXCLUDED_KEYWORDS = [
    "trailer",
    "teaser",
    "first look",
    "cast",
    "casting",
    "renewed",
    "cancelled",
    "canceled",
    "streaming on",
    "coming to",
    "moves to",
    "premiere date",
    "release date",
]
ALLOWED_FLAIRS = [
    "discussion",
    "review",
    "episode discussion",
    "weekly rec thread",
    "official",
]
BLOCKED_FLAIRS = ["trailer", "casting", "news", "premiere date"]
MIN_COMMENT_SCORE_RATIO = 0.1  # comments / score must be >= this

EPISODE_RE = re.compile(r"S\d{1,2}E\d{1,2}|Episode \d+|Season \d+", re.IGNORECASE)

logger = logging.getLogger(__name__)


def _is_episode_discussion(post: dict) -> bool:
    """Detects if a post is an episode discussion based on title or flair."""
    title = post.get("title", "")
    flair = post.get("flair", "")
    if EPISODE_RE.search(title) or EPISODE_RE.search(flair):
        return True
    if "episode discussion" in flair.lower():
        return True
    return False


def enrich_posts(posts: list[dict]) -> list[dict]:
    """Fetches additional metadata (score, comments, flair) from Reddit JSON API."""
    enriched_posts = []

    for post in posts:
        post_id = post["id"].replace("t3_", "")
        # Use .json endpoint for the post
        json_url = f"https://www.reddit.com/r/television/comments/{post_id}.json"

        try:
            logger.info(f"Enriching post {post_id}...")
            response = requests.get(
                json_url, headers={"User-Agent": USER_AGENT}, timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                # Reddit returns a 2-element array for post threads
                if isinstance(data, list) and len(data) > 0:
                    post_data = data[0]["data"]["children"][0]["data"]
                    post["score"] = post_data.get("score", 0)
                    post["num_comments"] = post_data.get("num_comments", 0)
                    post["flair"] = (post_data.get("link_flair_text") or "").strip()
            else:
                logger.warning(
                    f"Failed to enrich post {post_id}: HTTP {response.status_code}"
                )

        except Exception as e:
            logger.warning(f"Error enriching post {post_id}: {e}")

        enriched_posts.append(post)
        # Moderate rate limiting
        time.sleep(1.0)

    # Save enriched posts
    os.makedirs(ARTIFACT_DIR, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    artifact_path = os.path.join(ARTIFACT_DIR, f"enriched_posts_{timestamp}.json")
    with open(artifact_path, "w", encoding="utf-8") as f:
        json.dump(enriched_posts, f, indent=2)

    return enriched_posts


def filter_posts(posts: list[dict]) -> list[dict]:
    """Applies multiple filtering layers to keep only high-engagement threads."""
    original_count = len(posts)
    filtered = []

    for post in posts:
        # 1. Keyword filter
        title_lower = post["title"].lower()
        if any(kw in title_lower for kw in EXCLUDED_KEYWORDS):
            logger.info(f"Filtered (Keyword): {post['title']}")
            continue

        # 2. Flair filter
        flair_lower = post["flair"].lower()
        if post["flair"]:
            if flair_lower in BLOCKED_FLAIRS:
                logger.info(
                    f"Filtered (Blocked Flair): {post['title']} [{post['flair']}]"
                )
                continue
            if ALLOWED_FLAIRS and flair_lower not in ALLOWED_FLAIRS:
                logger.info(
                    f"Filtered (Disallowed Flair): {post['title']} [{post['flair']}]"
                )
                continue
        # If flair is empty, we keep it as per instructions Step 4.3.2

        # 3. Comment count filter
        # Episode Privilege: lower threshold for episode discussions
        is_episode = _is_episode_discussion(post)
        threshold = 20 if is_episode else MIN_COMMENTS

        if post["num_comments"] > 0 and post["num_comments"] < threshold:
            logger.info(
                f"Filtered (Low Comments): {post['title']} ({post['num_comments']} < {threshold})"
            )
            continue

        # 4. Engagement ratio filter
        # Episode Privilege: bypass ratio filter for episode discussions
        if not is_episode and post["score"] > 0:
            ratio = post["num_comments"] / post["score"]
            if ratio < MIN_COMMENT_SCORE_RATIO:
                logger.info(
                    f"Filtered (Low Ratio): {post['title']} (ratio {ratio:.2f})"
                )
                continue

        filtered.append(post)

    # Sort by comment count descending
    filtered.sort(key=lambda x: x["num_comments"], reverse=True)

    logger.info(
        f"Filtered {original_count} -> {len(filtered)} posts ({original_count - len(filtered)} removed)"
    )

    # Save filtered results
    os.makedirs(ARTIFACT_DIR, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    artifact_path = os.path.join(ARTIFACT_DIR, f"filtered_posts_{timestamp}.json")
    with open(artifact_path, "w", encoding="utf-8") as f:
        json.dump(filtered, f, indent=2)

    return filtered


def enrich_and_filter(posts: list[dict]) -> list[dict]:
    """Combined public function for orchestration."""
    enriched = enrich_posts(posts)
    filtered = filter_posts(enriched)
    return filtered
