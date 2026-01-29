import requests
import json
import time
import re
import os
import datetime
import logging

ARTIFACT_DIR = "data/artifacts"
USER_AGENT = "TheTV Signal/1.0 (RSS digest bot)"
MAX_COMMENTS_PER_POST = 3

logger = logging.getLogger(__name__)


def extract_comments(posts: list[dict]) -> list[dict]:
    """Fetches top comments for each filtered post and cleaned them up."""
    for post in posts:
        # Construct JSON URL with top sort and limit
        json_url = f"{post['url']}.json?sort=top&limit=10"

        try:
            logger.info(f"Extracting comments for post: {post['title'][:50]}...")
            response = requests.get(
                json_url, headers={"User-Agent": USER_AGENT}, timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                # response[1] contains the comments
                if isinstance(data, list) and len(data) > 1:
                    children = data[1]["data"]["children"]
                    raw_comments = []

                    for child in children:
                        if child["kind"] == "t1":  # t1 is comment
                            c_data = child["data"]
                            body = c_data.get("body", "")

                            # Clean body: truncate and remove markdown links
                            body = body[:500] + "..." if len(body) > 500 else body
                            # Replace [text](url) with just text
                            body = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", body)

                            raw_comments.append(
                                {
                                    "author": c_data.get("author", "[deleted]"),
                                    "body": body,
                                    "score": c_data.get("score", 0),
                                    "author_flair": c_data.get("author_flair_text", "") or "",
                                }
                            )

                    # Sort by score and take top MAX_COMMENTS_PER_POST
                    raw_comments.sort(key=lambda x: x["score"], reverse=True)
                    post["comments"] = raw_comments[:MAX_COMMENTS_PER_POST]
            else:
                logger.warning(
                    f"Failed to fetch comments for post {post['id']}: HTTP {response.status_code}"
                )
                post["comments"] = []
                post["comments_degraded"] = True

        except Exception as e:
            logger.warning(f"Failed to fetch comments for post {post['id']}: {e}")
            post["comments"] = []
            post["comments_degraded"] = True

        # Rate limiting
        time.sleep(1.0)

    # Save results to artifacts
    os.makedirs(ARTIFACT_DIR, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    artifact_path = os.path.join(ARTIFACT_DIR, f"posts_with_comments_{timestamp}.json")
    with open(artifact_path, "w", encoding="utf-8") as f:
        json.dump(posts, f, indent=2)

    return posts
