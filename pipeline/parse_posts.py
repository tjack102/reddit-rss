import feedparser
import html
import re
import logging
import json
import os
import datetime

ARTIFACT_DIR = "data/artifacts"

logger = logging.getLogger(__name__)


def parse(raw_xml: str) -> list[dict]:
    """Takes raw RSS XML and returns a list of structured post dictionaries."""
    try:
        feed = feedparser.parse(raw_xml)
        posts = []

        for entry in feed.entries:
            try:
                # Extract ID
                post_id = ""
                if hasattr(entry, "id"):
                    post_id = entry.id

                # If ID is a URL or missing, extract from link
                if not post_id or post_id.startswith("http"):
                    link = getattr(entry, "link", "")
                    match = re.search(r"/comments/([a-z0-9]+)", link)
                    if match:
                        post_id = f"t3_{match.group(1)}"

                if not post_id:
                    logger.warning(
                        f"Could not extract ID for entry: {getattr(entry, 'title', 'Unknown Title')}"
                    )
                    continue

                # Extract fields
                title = html.unescape(getattr(entry, "title", ""))
                url = getattr(entry, "link", "")

                author = "[deleted]"
                if hasattr(entry, "author_detail") and hasattr(
                    entry.author_detail, "name"
                ):
                    author = entry.author_detail.name
                elif hasattr(entry, "author"):
                    author = entry.author

                if author.startswith("/u/"):
                    author = author[3:]
                elif author.startswith("u/"):
                    author = author[2:]

                created = getattr(entry, "published", getattr(entry, "updated", ""))

                post = {
                    "id": post_id,
                    "title": title,
                    "url": url,
                    "score": 0,  # Populate later
                    "num_comments": 0,  # Populate later
                    "flair": "",  # Populate later
                    "author": author,
                    "created": created,
                    "subreddit": "television",
                }
                posts.append(post)

            except Exception as e:
                logger.warning(f"Failed to parse entry: {e}")
                continue

        # Save to artifacts
        os.makedirs(ARTIFACT_DIR, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        artifact_path = os.path.join(ARTIFACT_DIR, f"parsed_posts_{timestamp}.json")

        with open(artifact_path, "w", encoding="utf-8") as f:
            json.dump(posts, f, indent=2)

        logger.info(
            f"Successfully parsed {len(posts)} posts and saved to {artifact_path}"
        )
        return posts

    except Exception as e:
        logger.error(f"Failed to parse RSS XML: {e}")
        raise
