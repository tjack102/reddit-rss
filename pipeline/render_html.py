import jinja2
import datetime
import os
import re
import math
import logging

DIGEST_DIR = "data/digests"

logger = logging.getLogger(__name__)

# --- Sentiment keyword lists (#7) ---
POSITIVE_WORDS = {
    "amazing", "masterpiece", "brilliant", "fantastic", "incredible", "love",
    "loved", "perfect", "excellent", "outstanding", "phenomenal", "superb",
    "beautiful", "gorgeous", "stunning", "best", "favorite", "favourite",
    "great", "wonderful", "awesome", "enjoy", "enjoyed", "impressive",
}
NEGATIVE_WORDS = {
    "terrible", "awful", "horrible", "disappointing", "boring", "worst",
    "hate", "hated", "trash", "garbage", "mediocre", "bad", "poor",
    "painful", "unwatchable", "cringe", "annoying", "overrated", "weak",
    "bland", "dull", "forgettable", "disaster", "ruined",
}
MIXED_WORDS = {
    "but", "however", "although", "conflicted", "mixed", "uneven",
    "inconsistent", "divisive", "controversial", "overrated",
}

# --- Creator detection keywords (#34) ---
CREATOR_FLAIR_KEYWORDS = {
    "creator", "showrunner", "writer", "director", "producer", "actor",
    "actress", "verified", "official", "staff", "crew", "show creator",
}

# --- Spoiler keywords (#20) ---
SPOILER_KEYWORDS = {
    "finale", "twist", "dies", "death", "killed", "ending", "spoiler",
    "reveal", "plot twist", "cliffhanger",
}
SPOILER_EPISODE_RE = re.compile(r"S\d{2}E\d{2}", re.IGNORECASE)


def _compute_sentiment(comments):
    """Simple keyword sentiment for a post's comments. Returns label + css class."""
    if not comments:
        return {"label": "Neutral discussion", "emoji": "\U0001f4ac", "css": "neutral"}
    pos = 0
    neg = 0
    mix = 0
    for c in comments:
        words = set(re.findall(r"[a-z]+", c.get("body", "").lower()))
        pos += len(words & POSITIVE_WORDS)
        neg += len(words & NEGATIVE_WORDS)
        mix += len(words & MIXED_WORDS)
    total = pos + neg + mix
    if total == 0:
        return {"label": "Neutral discussion", "emoji": "\U0001f4ac", "css": "neutral"}
    if pos > neg * 2 and pos > mix:
        return {"label": "Positive vibes", "emoji": "\U0001f60d", "css": "positive"}
    if neg > pos * 2 and neg > mix:
        return {"label": "Critical reception", "emoji": "\U0001f62c", "css": "negative"}
    if mix >= pos and mix >= neg:
        return {"label": "Mixed reactions", "emoji": "\u2696\ufe0f", "css": "mixed"}
    if abs(pos - neg) <= 2:
        return {"label": "Mixed reactions", "emoji": "\u2696\ufe0f", "css": "mixed"}
    if pos > neg:
        return {"label": "Positive vibes", "emoji": "\U0001f60d", "css": "positive"}
    return {"label": "Critical reception", "emoji": "\U0001f62c", "css": "negative"}


def _compute_consensus(comments):
    """Agreement vs disagreement detection (#26). Returns label or None if < 5 comments."""
    if not comments or len(comments) < 2:
        return None
    agree_words = {"agree", "exactly", "this", "yes", "right", "same", "true", "absolutely", "definitely"}
    disagree_words = {"disagree", "wrong", "no", "nah", "nope", "but", "however", "actually"}
    agree = 0
    disagree = 0
    for c in comments:
        words = set(re.findall(r"[a-z]+", c.get("body", "").lower()))
        agree += len(words & agree_words)
        disagree += len(words & disagree_words)
    total = agree + disagree
    if total < 3:
        return None
    pct = round(agree / total * 100)
    if pct >= 70:
        return {"label": f"Strong Consensus ({pct}% alignment)", "emoji": "\u2705", "css": "consensus"}
    if pct <= 30:
        return {"label": f"Divided Community ({100 - pct}% split)", "emoji": "\u26a1", "css": "divided"}
    return {"label": f"Divided Community ({max(pct, 100-pct)}% split)", "emoji": "\u26a1", "css": "divided"}


def _extract_show_name(title):
    """Extract show name from post title (#22). Returns string or empty."""
    # Pattern: "Show Name S01E02" or "Show Name - Season 1"
    m = re.match(r"^(.+?)\s+S\d{1,2}E\d{1,2}", title, re.IGNORECASE)
    if m:
        return m.group(1).strip().strip('"').strip("'")
    m = re.match(r"^(.+?)\s*[-–—]\s*(?:Season|Series)\s+\d", title, re.IGNORECASE)
    if m:
        return m.group(1).strip().strip('"').strip("'")
    # Pattern: quoted show name at start
    m = re.match(r'^["\'](.+?)["\']', title)
    if m:
        return m.group(1).strip()
    return ""


def _reading_time(post):
    """Estimate reading time in minutes (#23)."""
    words = len(post.get("title", "").split())
    for c in post.get("comments", []):
        words += len(c.get("body", "").split())
    return max(1, math.ceil(words / 200))


def _is_creator_comment(comment):
    """Check if comment author flair suggests industry person (#34)."""
    flair = comment.get("author_flair", "").lower()
    if not flair:
        return False
    return any(kw in flair for kw in CREATOR_FLAIR_KEYWORDS)


def _has_spoiler(post):
    """Check if post likely contains spoilers (#20)."""
    title_lower = post.get("title", "").lower()
    flair_lower = post.get("flair", "").lower()
    if "spoiler" in flair_lower:
        return True
    if SPOILER_EPISODE_RE.search(post.get("title", "")):
        return True
    return any(kw in title_lower for kw in SPOILER_KEYWORDS)


def _enrich_posts_for_template(posts):
    """Pre-process posts to add all computed feature data."""
    total_comments = 0
    for post in posts:
        # Sentiment (#7)
        post["sentiment"] = _compute_sentiment(post.get("comments", []))

        # Consensus (#26)
        post["consensus"] = _compute_consensus(post.get("comments", []))

        # Show name (#22)
        post["show_name"] = _extract_show_name(post.get("title", ""))

        # Reading time (#23)
        post["reading_time"] = _reading_time(post)

        # Spoiler detection (#20)
        post["has_spoiler"] = _has_spoiler(post)

        # Creator comments (#34)
        for c in post.get("comments", []):
            c["is_creator"] = _is_creator_comment(c)

        # Conversation catalyst (#19) — top-voted comment
        comments = post.get("comments", [])
        if comments:
            top = max(comments, key=lambda c: c.get("score", 0))
            top["is_catalyst"] = True

        # Freshness (#3) — hours since created
        try:
            created = datetime.datetime.fromisoformat(post["created"].replace("Z", "+00:00"))
            now = datetime.datetime.now(datetime.timezone.utc)
            delta = now - created
            hours = delta.total_seconds() / 3600
            post["hours_ago"] = hours
            if hours < 1:
                post["time_ago"] = "just now"
            elif hours < 24:
                post["time_ago"] = f"{int(hours)}h ago"
            elif hours < 48:
                post["time_ago"] = "yesterday"
            else:
                post["time_ago"] = f"{int(hours / 24)}d ago"
            post["is_trending"] = hours < 6 and post.get("num_comments", 0) >= 200
        except Exception:
            post["time_ago"] = ""
            post["hours_ago"] = 999
            post["is_trending"] = False

        total_comments += post.get("num_comments", 0)

    return posts, total_comments


def render(posts: list[dict], metrics: dict | None = None) -> str:
    """Generates the final HTML digest file using Jinja2."""
    try:
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader("templates"),
            autoescape=jinja2.select_autoescape(["html"]),
        )
        template = env.get_template("digest.html")

        # Determine if the digest is in degraded mode
        degraded = (
            all(post.get("comments_degraded", False) for post in posts)
            if posts
            else False
        )

        # Enrich posts with computed feature data
        posts, total_comments = _enrich_posts_for_template(posts)

        # Find hottest post (#6 stats dashboard)
        hottest = max(posts, key=lambda p: p.get("num_comments", 0)) if posts else None

        # Metrics for stats dashboard (#6, #33)
        m = metrics or {}
        posts_fetched = m.get("posts_fetched", 0)
        posts_filtered_out = posts_fetched - len(posts) if posts_fetched else 0

        html = template.render(
            posts=posts,
            date=datetime.datetime.now().strftime("%A, %B %d, %Y"),
            generated_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S EST"),
            degraded=degraded,
            total_comments=total_comments,
            hottest_title=hottest["title"] if hottest else "",
            hottest_comments=hottest.get("num_comments", 0) if hottest else 0,
            posts_filtered_out=posts_filtered_out,
            posts_fetched=posts_fetched,
        )

        os.makedirs(DIGEST_DIR, exist_ok=True)
        date_str = datetime.datetime.now().strftime("%Y%m%d")
        file_path = os.path.join(DIGEST_DIR, f"digest_{date_str}.html")
        latest_path = os.path.join(DIGEST_DIR, "latest.html")

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(html)

        with open(latest_path, "w", encoding="utf-8") as f:
            f.write(html)

        file_size_kb = len(html) / 1024
        logger.info(f"Digest written to {file_path} ({file_size_kb:.1f} KB)")

        return file_path

    except Exception as e:
        logger.error(f"Failed to render digest: {e}")
        raise


def render_fallback_digest(error_message: str) -> str:
    """Generates a minimal HTML fallback page when something goes wrong."""
    try:
        date_str_display = datetime.datetime.now().strftime("%A, %B %d, %Y")
        html = f"""
        <!DOCTYPE html>
        <html>
        <head><title>The TV Signal — {date_str_display}</title></head>
        <body style="font-family: sans-serif; padding: 40px; text-align: center;">
            <h1>The TV Signal</h1>
            <p>Today's digest could not be generated.</p>
            <p style="color: #666; font-style: italic;">Error: {error_message}</p>
            <p>Normal service will resume with the next run.</p>
        </body>
        </html>
        """

        os.makedirs(DIGEST_DIR, exist_ok=True)
        date_str = datetime.datetime.now().strftime("%Y%m%d")
        file_path = os.path.join(DIGEST_DIR, f"digest_{date_str}_fallback.html")
        latest_path = os.path.join(DIGEST_DIR, "latest.html")

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(html)
        with open(latest_path, "w", encoding="utf-8") as f:
            f.write(html)

        return file_path

    except Exception as e:
        logger.critical(f"Even fallback render failed: {e}")
        # Last resort: plain text
        try:
            path = os.path.join(DIGEST_DIR, "error.txt")
            with open(path, "w") as f:
                f.write(f"FATAL ERROR: {error_message}")
            return path
        except:
            return "data/digests/error.txt"
