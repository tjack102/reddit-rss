# The TV Signal - Implementation Instructions

These are step-by-step instructions to build The TV Signal from scratch. Follow them in order. Every file, every function, every line of logic is described. Do not skip steps.

---

## Phase 0: Project Scaffolding

### Step 0.1: Create the directory structure

```
tv-signal/
├── pipeline/
│   ├── __init__.py
│   ├── fetch_rss.py
│   ├── parse_posts.py
│   ├── deduplicate.py
│   ├── filter_posts.py
│   ├── extract_comments.py
│   ├── render_html.py
│   └── update_memory.py
├── templates/
│   └── digest.html
├── data/
│   ├── seen_ids.json          (created at runtime)
│   ├── artifacts/             (created at runtime)
│   └── digests/               (created at runtime)
├── logs/
│   └── (created at runtime)
├── run_digest.py
├── requirements.txt
├── CLAUDE.md
├── README.md
└── .gitignore
```

Create every directory listed above. Create `__init__.py` as an empty file. The `data/`, `logs/`, `data/artifacts/`, and `data/digests/` directories must exist but will be populated at runtime.

### Step 0.2: Create `requirements.txt`

```
feedparser==6.0.11
requests==2.31.0
jinja2==3.1.4
```

No other dependencies. Standard library handles everything else (json, datetime, logging, os, pathlib, time, hashlib).

### Step 0.3: Create `.gitignore`

```
__pycache__/
*.pyc
.env
data/artifacts/
data/digests/
logs/
venv/
```

Do NOT ignore `data/seen_ids.json` or `CLAUDE.md` — these are persistent state files that must be committed and backed up.

### Step 0.4: Install dependencies

```bash
pip install -r requirements.txt
```

---

## Phase 1: Task 1 — Fetch RSS Feed (`pipeline/fetch_rss.py`)

This script fetches the raw RSS XML from Reddit and saves it to disk as an artifact.

### Step 1.1: Define the module

Create `pipeline/fetch_rss.py` with these exact constants at the top:

```python
RSS_URL = "https://www.reddit.com/r/television/.rss"
USER_AGENT = "TheTV Signal/1.0 (RSS digest bot)"
ARTIFACT_DIR = "data/artifacts"
```

Reddit blocks requests without a User-Agent header. This is critical.

### Step 1.2: Implement `fetch()` function

The function must:

1. Import `requests`, `os`, `datetime`, `logging`.
2. Create `ARTIFACT_DIR` if it doesn't exist using `os.makedirs(ARTIFACT_DIR, exist_ok=True)`.
3. Make a GET request to `RSS_URL` with headers `{"User-Agent": USER_AGENT}`.
4. Set a timeout of 30 seconds on the request.
5. Check `response.status_code`. If not 200, raise an exception with the status code and response text.
6. Save the raw response text to `{ARTIFACT_DIR}/raw_feed_{timestamp}.xml` where timestamp is `datetime.datetime.now().strftime("%Y%m%d_%H%M%S")`.
7. Log the number of bytes fetched and the artifact file path.
8. Return the raw XML string (response.text).

### Step 1.3: Error handling

Wrap the entire request in a try/except block:
- Catch `requests.exceptions.Timeout` → log "RSS fetch timed out after 30s", re-raise.
- Catch `requests.exceptions.ConnectionError` → log "Cannot reach Reddit RSS", re-raise.
- Catch `requests.exceptions.RequestException` as generic fallback → log the error, re-raise.

All exceptions must propagate up to the orchestrator. This script does NOT handle fallback logic — the orchestrator does.

### Step 1.4: Return signature

```python
def fetch() -> str:
    """Fetches RSS feed XML. Returns raw XML string. Raises on failure."""
```

---

## Phase 2: Task 2 — Parse Posts (`pipeline/parse_posts.py`)

This script takes raw RSS XML and returns a list of structured post dictionaries.

### Step 2.1: Define the data structure

Each parsed post is a dictionary with these exact keys:

```python
{
    "id": str,          # Reddit post ID (e.g., "t3_abc123"), extracted from the <id> or <link> tag
    "title": str,       # Post title, HTML-unescaped
    "url": str,         # Full Reddit URL to the post
    "score": int,       # Upvote score (from RSS if available, else 0)
    "num_comments": int, # Comment count (from RSS if available, else 0)
    "flair": str,       # Post flair text (from RSS if available, else "")
    "author": str,      # Author username
    "created": str,     # ISO 8601 timestamp string
    "subreddit": str,   # Always "television" for MVP
}
```

### Step 2.2: Implement `parse(raw_xml: str) -> list[dict]`

1. Import `feedparser` and `html`, `re`, `logging`.
2. Call `feedparser.parse(raw_xml)`.
3. Access `feed.entries` — this is a list of entry objects.
4. For each entry, extract fields:
   - `id`: Use `entry.id` if present. Reddit RSS entries have an `id` field that looks like `t3_xxxxxx`. If `entry.id` is a URL, extract the post ID from the URL path (the last segment after `/comments/`). Use a regex: `r'/comments/([a-z0-9]+)'` applied to `entry.link`.
   - `title`: Use `entry.title`. Apply `html.unescape()` to decode HTML entities like `&amp;`.
   - `url`: Use `entry.link`.
   - `author`: Use `entry.author` if present. Reddit RSS uses `entry.author_detail.name` or the `/u/username` format. Strip the `/u/` prefix. Default to `"[deleted]"` if missing.
   - `created`: Use `entry.published` if present, else `entry.updated`, else empty string.
   - `flair`: Reddit RSS does NOT include flair in the standard feed. Set to `""` for now. Flair will be extracted later via the Reddit API in the comment extraction step if possible.
   - `score`: Reddit RSS does NOT include score. Set to `0`. Will be populated later.
   - `num_comments`: Reddit RSS does NOT include comment count. Set to `0`. Will be populated later.
   - `subreddit`: Hardcode `"television"`.
5. Skip entries where `id` extraction fails (log a warning).
6. Save parsed posts as JSON to `data/artifacts/parsed_posts_{timestamp}.json`.
7. Log the count of successfully parsed posts.
8. Return the list of post dicts.

### Step 2.3: Important note about RSS limitations

Reddit's RSS feed provides: title, link, author, published date, and a content snippet. It does NOT provide: score, comment count, or flair. These fields are initialized to defaults and enriched in later pipeline steps (filter and comment extraction) via the Reddit JSON API.

---

## Phase 3: Task 3 — Deduplicate (`pipeline/deduplicate.py`)

This script removes posts that appeared in previous digests.

### Step 3.1: Define constants

```python
SEEN_IDS_FILE = "data/seen_ids.json"
MAX_SEEN_IDS = 200
```

### Step 3.2: Implement `load_seen_ids() -> list[str]`

1. Check if `SEEN_IDS_FILE` exists.
2. If it exists, read it and parse as JSON. It will be a JSON array of string IDs.
3. If it does not exist or is corrupted (invalid JSON), return an empty list and log a warning.
4. Return the list.

### Step 3.3: Implement `save_seen_ids(ids: list[str]) -> None`

1. Take the list of IDs.
2. If the list is longer than `MAX_SEEN_IDS`, slice to keep only the last 200: `ids = ids[-MAX_SEEN_IDS:]`.
3. Write the list as JSON to `SEEN_IDS_FILE` with indent=2 for readability.

### Step 3.4: Implement `deduplicate(posts: list[dict]) -> list[dict]`

1. Load seen IDs via `load_seen_ids()`.
2. Convert seen IDs to a set for O(1) lookup.
3. Filter: keep only posts where `post["id"]` is NOT in the seen set.
4. Log how many posts were removed as duplicates and how many remain.
5. Do NOT save seen IDs here — that happens in Task 7 (update memory) after the digest is successfully generated.
6. Return the filtered list.

---

## Phase 4: Task 4 — Filter Posts (`pipeline/filter_posts.py`)

This script applies multi-layer filtering to keep only high-engagement discussion threads.

### Step 4.1: Define filter constants

```python
MIN_COMMENTS = 50
EXCLUDED_KEYWORDS = [
    "trailer", "teaser", "first look",
    "cast", "casting", "renewed", "cancelled", "canceled",
    "streaming on", "coming to", "moves to",
    "premiere date", "release date",
]
ALLOWED_FLAIRS = ["discussion", "review", "episode discussion"]
BLOCKED_FLAIRS = ["trailer", "casting", "news", "premiere date"]
MIN_COMMENT_SCORE_RATIO = 0.1  # comments / score must be >= this
```

### Step 4.2: Enrichment step — fetch metadata from Reddit JSON API

Before filtering, the pipeline needs comment counts and scores that RSS doesn't provide. Implement `enrich_posts(posts: list[dict]) -> list[dict]`:

1. For each post, construct the Reddit JSON URL: `https://www.reddit.com/r/television/comments/{post_id_without_t3_prefix}.json`
   - Strip the `t3_` prefix from the post ID if present.
   - Alternatively use the post URL and append `.json`: `post["url"] + ".json"`
2. Make a GET request with the same User-Agent header as the RSS fetcher.
3. **Rate limiting is critical:** Add a `time.sleep(1.0)` between each request. Reddit rate-limits to ~60 requests/minute for unauthenticated requests. With sleep(1.0) you stay safely under this.
4. Parse the JSON response. Reddit returns a 2-element array:
   - `response[0]["data"]["children"][0]["data"]` contains the post metadata.
   - Extract: `score`, `num_comments`, `link_flair_text`.
5. Update the post dict with these enriched values:
   - `post["score"] = data["score"]`
   - `post["num_comments"] = data["num_comments"]`
   - `post["flair"] = (data.get("link_flair_text") or "").strip()`
6. If the request fails for a specific post (timeout, 404, rate limited), log a warning and keep the post with its default values (score=0, num_comments=0). Do not crash.
7. Save enriched posts to `data/artifacts/enriched_posts_{timestamp}.json`.

**Performance note:** If there are 25 posts, this step takes ~25 seconds due to rate limiting. This is the slowest step in the pipeline and is acceptable within the 5-minute budget.

### Step 4.3: Implement `filter_posts(posts: list[dict]) -> list[dict]`

Apply filters in this order. Each filter logs how many posts it removed:

1. **Keyword filter:** Remove posts where any keyword from `EXCLUDED_KEYWORDS` appears in `post["title"].lower()`. Use substring matching, not word boundary matching.

2. **Flair filter:** If `post["flair"]` is non-empty:
   - If `post["flair"].lower()` is in `BLOCKED_FLAIRS`, remove the post.
   - If `ALLOWED_FLAIRS` is defined and `post["flair"].lower()` is NOT in `ALLOWED_FLAIRS`, remove the post.
   - If `post["flair"]` is empty (RSS didn't provide it and enrichment failed), **keep the post** — do not penalize missing data.

3. **Comment count filter:** Remove posts where `post["num_comments"] < MIN_COMMENTS`. If `num_comments` is still 0 (enrichment failed), **keep the post** — better to include uncertain posts than miss good discussions.

4. **Engagement ratio filter:** If `post["score"] > 0`, calculate `ratio = post["num_comments"] / post["score"]`. Remove posts where `ratio < MIN_COMMENT_SCORE_RATIO`. This catches promotional posts that get upvotes but no discussion. If score is 0, skip this filter for that post.

5. Log summary: "Filtered {original_count} → {filtered_count} posts ({removed_count} removed)"

6. Sort remaining posts by `num_comments` descending (most-discussed first).

7. Save filtered results to `data/artifacts/filtered_posts_{timestamp}.json`.

8. Return filtered list.

### Step 4.4: Implement the combined `enrich_and_filter(posts: list[dict]) -> list[dict]`

This is the public function called by the orchestrator:

```python
def enrich_and_filter(posts: list[dict]) -> list[dict]:
    enriched = enrich_posts(posts)
    filtered = filter_posts(enriched)
    return filtered
```

---

## Phase 5: Task 5 — Extract Comments (`pipeline/extract_comments.py`)

This script fetches the top comments for each filtered post.

### Step 5.1: Define constants

```python
MAX_COMMENTS_PER_POST = 3
USER_AGENT = "TheTVSignal/1.0 (RSS digest bot)"
```

### Step 5.2: Implement `extract_comments(posts: list[dict]) -> list[dict]`

For each post in the list:

1. Construct the Reddit JSON URL: `post["url"] + ".json?sort=top&limit=10"`.
   - `sort=top` returns the highest-voted comments.
   - `limit=10` fetches enough to filter from.
2. Make a GET request with User-Agent header and 30-second timeout.
3. Add `time.sleep(1.0)` between requests for rate limiting.
4. Parse the response:
   - `response[1]["data"]["children"]` is the list of top-level comments.
   - Each comment: `child["data"]` has `body`, `score`, `author`, `created_utc`.
5. Filter out comments where `child["kind"] != "t1"` (skip "more comments" stubs which have kind `"more"`).
6. Take the top `MAX_COMMENTS_PER_POST` comments by score.
7. For each comment, create a dict:
   ```python
   {
       "author": str,   # comment author username
       "body": str,     # comment text (raw markdown from Reddit)
       "score": int,    # comment upvote score
   }
   ```
8. Strip the comment body:
   - Truncate to 500 characters max. If truncated, append "..."
   - Remove any markdown links, replacing `[text](url)` with just `text` using regex: `re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', body)`
9. Add a `"comments"` key to the post dict containing the list of comment dicts.

### Step 5.3: Graceful degradation

If the request fails for a post (any exception):

1. Log a warning: "Failed to fetch comments for post {post_id}: {error}"
2. Set `post["comments"] = []` (empty list).
3. Set `post["comments_degraded"] = True` (flag for the template).
4. Continue to the next post. Do NOT crash the pipeline.

If ALL comment fetches fail:

1. Log an error: "All comment fetches failed — digest will be generated in degraded mode."
2. Every post will have `comments_degraded = True`.
3. The HTML template will show a notice about degraded mode (handled in the render step).

### Step 5.4: Return value

The function returns the same list of post dicts, now augmented with `"comments"` and optionally `"comments_degraded"` keys.

Save to `data/artifacts/posts_with_comments_{timestamp}.json`.

---

## Phase 6: Task 6 — Render HTML Digest (`pipeline/render_html.py`)

This script generates the final HTML digest file.

### Step 6.1: Create the Jinja2 template

Create `templates/digest.html` with this exact content:

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>The TV Signal — {{ date }}</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    line-height: 1.6;
    color: #222;
    background: #f5f5f5;
    padding: 16px;
    max-width: 640px;
    margin: 0 auto;
  }
  .header {
    text-align: center;
    padding: 24px 0 16px;
    border-bottom: 2px solid #333;
    margin-bottom: 24px;
  }
  .header h1 { font-size: 24px; font-weight: 700; }
  .header .date { font-size: 14px; color: #666; margin-top: 4px; }
  .header .stats { font-size: 13px; color: #888; margin-top: 4px; }
  .degraded-notice {
    background: #fff3cd;
    border: 1px solid #ffc107;
    border-radius: 6px;
    padding: 12px 16px;
    margin-bottom: 20px;
    font-size: 14px;
    color: #856404;
  }
  .post {
    background: #fff;
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 16px;
    border: 1px solid #e0e0e0;
  }
  .post-title {
    font-size: 17px;
    font-weight: 600;
    color: #1a1a1a;
    text-decoration: none;
    display: block;
    margin-bottom: 6px;
  }
  .post-title:hover { color: #0066cc; }
  .post-meta {
    font-size: 13px;
    color: #888;
    margin-bottom: 10px;
  }
  .post-meta span { margin-right: 12px; }
  .flair {
    display: inline-block;
    background: #e8e8e8;
    color: #555;
    padding: 1px 8px;
    border-radius: 12px;
    font-size: 12px;
    margin-left: 4px;
  }
  .comments-section {
    border-top: 1px solid #eee;
    padding-top: 10px;
    margin-top: 10px;
  }
  .comment {
    padding: 8px 0 8px 12px;
    border-left: 3px solid #e0e0e0;
    margin-bottom: 8px;
    font-size: 14px;
  }
  .comment-meta {
    font-size: 12px;
    color: #999;
    margin-bottom: 4px;
  }
  .comment-body {
    color: #333;
    word-wrap: break-word;
  }
  .footer {
    text-align: center;
    padding: 24px 0;
    font-size: 13px;
    color: #999;
    border-top: 1px solid #ddd;
    margin-top: 8px;
  }
  .footer a { color: #666; }
</style>
</head>
<body>
  <div class="header">
    <h1>The TV Signal</h1>
    <div class="date">{{ date }}</div>
    <div class="stats">{{ posts | length }} threads · /r/television</div>
  </div>

  {% if degraded %}
  <div class="degraded-notice">
    ⚠ Comments are temporarily unavailable. This digest shows thread metadata only. Normal service will resume with the next run.
  </div>
  {% endif %}

  {% for post in posts %}
  <div class="post">
    <a class="post-title" href="{{ post.url }}" target="_blank">{{ post.title }}</a>
    <div class="post-meta">
      <span>▲ {{ post.score }}</span>
      <span>💬 {{ post.num_comments }}</span>
      <span>by {{ post.author }}</span>
      {% if post.flair %}<span class="flair">{{ post.flair }}</span>{% endif %}
    </div>

    {% if post.comments and post.comments | length > 0 %}
    <div class="comments-section">
      {% for comment in post.comments %}
      <div class="comment">
        <div class="comment-meta">{{ comment.author }} · ▲ {{ comment.score }}</div>
        <div class="comment-body">{{ comment.body }}</div>
      </div>
      {% endfor %}
    </div>
    {% elif post.comments_degraded %}
    <div class="comments-section">
      <div class="comment" style="color: #999; font-style: italic;">Comments unavailable for this thread.</div>
    </div>
    {% endif %}
  </div>
  {% endfor %}

  {% if posts | length == 0 %}
  <div class="post" style="text-align: center; color: #888;">
    No high-engagement discussions found today. Check back tomorrow.
  </div>
  {% endif %}

  <div class="footer">
    Generated by <a href="#">The TV Signal</a> · {{ generated_at }}
  </div>
</body>
</html>
```

### Step 6.2: Implement `render(posts: list[dict]) -> str`

1. Import `jinja2`, `datetime`, `os`, `logging`.
2. Set up the Jinja2 environment:
   ```python
   env = jinja2.Environment(
       loader=jinja2.FileSystemLoader("templates"),
       autoescape=jinja2.select_autoescape(["html"]),
   )
   template = env.get_template("digest.html")
   ```
3. Determine if the digest is in degraded mode:
   ```python
   degraded = all(post.get("comments_degraded", False) for post in posts) if posts else False
   ```
4. Render the template:
   ```python
   html = template.render(
       posts=posts,
       date=datetime.datetime.now().strftime("%A, %B %d, %Y"),
       generated_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S EST"),
       degraded=degraded,
   )
   ```
5. Create `data/digests/` directory if it doesn't exist.
6. Write the HTML to `data/digests/digest_{date}.html` where date is `YYYYMMDD` format.
7. Also write to `data/digests/latest.html` (always overwrite) so there's a stable path to the most recent digest.
8. Log the file path and file size in KB.
9. Return the file path to the digest.

### Step 6.3: Fallback digest

Implement `render_fallback_digest(error_message: str) -> str`:

1. Generate a minimal HTML page that says:
   - "The TV Signal — {date}"
   - "Today's digest could not be generated."
   - The error message.
   - "Normal service will resume with the next run."
2. Write this to `data/digests/digest_{date}_fallback.html` and also to `data/digests/latest.html`.
3. Return the file path.
4. This function must NEVER raise an exception — wrap everything in try/except and if even this fails, write a plain text file.

---

## Phase 7: Task 7 — Update Memory (`pipeline/update_memory.py`)

This script persists state after a successful digest generation.

### Step 7.1: Implement `update_memory(posts: list[dict], run_metrics: dict) -> None`

**Part A — Update seen IDs:**

1. Import `load_seen_ids` and `save_seen_ids` from `pipeline.deduplicate`.
2. Load current seen IDs.
3. Append all post IDs from the current digest: `new_ids = current_ids + [p["id"] for p in posts]`.
4. Call `save_seen_ids(new_ids)` — this handles the 200-ID rolling window truncation.

**Part B — Update CLAUDE.md:**

1. Read the current `CLAUDE.md` file.
2. Update (or create) a section called `## Last Run` with:
   ```
   ## Last Run
   - Date: {ISO 8601 timestamp}
   - Posts fetched: {count from RSS}
   - Posts after dedup: {count}
   - Posts after filter: {count}
   - Posts in digest: {count}
   - Comments fetched: {success_count}/{total_count}
   - Degraded mode: {yes/no}
   - Runtime: {seconds}s
   - Status: {success/partial/failed}
   ```
3. The `run_metrics` dict should contain all these values. It is assembled by the orchestrator and passed in.

**Part C — Update CLAUDE.md run history:**

1. Append a single line to a `## Run History` section:
   ```
   - {date} | {post_count} posts | {runtime}s | {status}
   ```
2. Keep only the last 30 entries in run history. If there are more, remove the oldest.

### Step 7.2: CLAUDE.md initial structure

Create `CLAUDE.md` with this initial content if it doesn't exist:

```markdown
# The TV Signal — Project Memory

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
```

---

## Phase 8: The Orchestrator (`run_digest.py`)

This is the main entry point that runs the 7-task pipeline serially.

### Step 8.1: Set up logging

At the very top of the script, configure logging before any imports from `pipeline/`:

```python
import logging
import os
import sys
import time
import datetime
import json
import traceback

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

log_filename = f"{LOG_DIR}/run_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(log_filename),
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger("orchestrator")
```

This ensures every `logging.info()` / `logging.warning()` / `logging.error()` call in any pipeline module writes to both the log file and stdout.

### Step 8.2: Implement the pipeline execution

```python
def run_pipeline():
    start_time = time.time()
    metrics = {
        "date": datetime.datetime.now().isoformat(),
        "posts_fetched": 0,
        "posts_after_dedup": 0,
        "posts_after_filter": 0,
        "posts_in_digest": 0,
        "comments_success": 0,
        "comments_total": 0,
        "degraded": False,
        "runtime": 0,
        "status": "failed",
    }
```

### Step 8.3: Task 1 — Fetch

```python
    logger.info("=" * 60)
    logger.info("TASK 1/7: Fetch RSS Feed")
    logger.info("=" * 60)
    try:
        from pipeline.fetch_rss import fetch
        raw_xml = fetch()
    except Exception as e:
        logger.error(f"FATAL: RSS fetch failed: {e}")
        logger.error(traceback.format_exc())
        # Generate fallback digest
        from pipeline.render_html import render_fallback_digest
        path = render_fallback_digest(f"RSS feed fetch failed: {e}")
        logger.info(f"Fallback digest written to {path}")
        metrics["runtime"] = round(time.time() - start_time, 2)
        metrics["status"] = "failed"
        _save_metrics(metrics)
        return metrics
```

If the RSS fetch fails, the entire pipeline stops and a fallback digest is generated. No point continuing without data.

### Step 8.4: Task 2 — Parse

```python
    logger.info("=" * 60)
    logger.info("TASK 2/7: Parse Posts")
    logger.info("=" * 60)
    try:
        from pipeline.parse_posts import parse
        posts = parse(raw_xml)
        metrics["posts_fetched"] = len(posts)
    except Exception as e:
        logger.error(f"FATAL: Parse failed: {e}")
        logger.error(traceback.format_exc())
        from pipeline.render_html import render_fallback_digest
        path = render_fallback_digest(f"RSS parsing failed: {e}")
        metrics["runtime"] = round(time.time() - start_time, 2)
        _save_metrics(metrics)
        return metrics
```

### Step 8.5: Task 3 — Deduplicate

```python
    logger.info("=" * 60)
    logger.info("TASK 3/7: Deduplicate")
    logger.info("=" * 60)
    try:
        from pipeline.deduplicate import deduplicate
        posts = deduplicate(posts)
        metrics["posts_after_dedup"] = len(posts)
    except Exception as e:
        logger.warning(f"Dedup failed, continuing with all posts: {e}")
        metrics["posts_after_dedup"] = len(posts)
```

Deduplication failure is NOT fatal. If the seen_ids file is corrupted, just process all posts. Better to show duplicates than show nothing.

### Step 8.6: Task 4 — Filter

```python
    logger.info("=" * 60)
    logger.info("TASK 4/7: Enrich & Filter")
    logger.info("=" * 60)
    try:
        from pipeline.filter_posts import enrich_and_filter
        posts = enrich_and_filter(posts)
        metrics["posts_after_filter"] = len(posts)
    except Exception as e:
        logger.warning(f"Filter failed, continuing with deduped posts: {e}")
        metrics["posts_after_filter"] = len(posts)
```

Filter failure is NOT fatal. If the Reddit API is down, skip enrichment and filtering — show all deduplicated posts with whatever metadata RSS provided.

### Step 8.7: Task 5 — Extract Comments

```python
    logger.info("=" * 60)
    logger.info("TASK 5/7: Extract Comments")
    logger.info("=" * 60)
    try:
        from pipeline.extract_comments import extract_comments
        posts = extract_comments(posts)
        metrics["comments_total"] = len(posts)
        metrics["comments_success"] = sum(1 for p in posts if p.get("comments") and len(p["comments"]) > 0)
        metrics["degraded"] = metrics["comments_success"] == 0
    except Exception as e:
        logger.warning(f"Comment extraction failed entirely: {e}")
        for p in posts:
            p["comments"] = []
            p["comments_degraded"] = True
        metrics["degraded"] = True
```

Comment extraction failure is NOT fatal. Mark all posts as degraded and continue to render.

### Step 8.8: Task 6 — Render

```python
    logger.info("=" * 60)
    logger.info("TASK 6/7: Render HTML Digest")
    logger.info("=" * 60)
    try:
        from pipeline.render_html import render
        digest_path = render(posts)
        metrics["posts_in_digest"] = len(posts)
        logger.info(f"Digest written to {digest_path}")
    except Exception as e:
        logger.error(f"Render failed: {e}")
        logger.error(traceback.format_exc())
        from pipeline.render_html import render_fallback_digest
        digest_path = render_fallback_digest(f"Render failed: {e}")
        metrics["status"] = "failed"
```

### Step 8.9: Task 7 — Update Memory

```python
    logger.info("=" * 60)
    logger.info("TASK 7/7: Update Memory")
    logger.info("=" * 60)
    try:
        from pipeline.update_memory import update_memory
        metrics["runtime"] = round(time.time() - start_time, 2)
        metrics["status"] = "success" if not metrics["degraded"] else "partial"
        update_memory(posts, metrics)
    except Exception as e:
        logger.error(f"Memory update failed: {e}")
        metrics["status"] = "partial"
```

Memory update failure is NOT fatal. The digest was already written to disk.

### Step 8.10: Final logging and return

```python
    metrics["runtime"] = round(time.time() - start_time, 2)
    logger.info("=" * 60)
    logger.info(f"Pipeline complete in {metrics['runtime']}s — Status: {metrics['status']}")
    logger.info(f"Posts: {metrics['posts_fetched']} fetched → {metrics['posts_after_filter']} filtered → {metrics['posts_in_digest']} in digest")
    logger.info("=" * 60)
    _save_metrics(metrics)
    return metrics
```

### Step 8.11: Implement `_save_metrics(metrics: dict)`

Save the metrics dict to `data/artifacts/run_metrics_{timestamp}.json` for debugging.

### Step 8.12: Main entry point

```python
if __name__ == "__main__":
    try:
        result = run_pipeline()
        if result["status"] == "failed":
            sys.exit(1)
    except Exception as e:
        logger.critical(f"Unhandled exception in orchestrator: {e}")
        logger.critical(traceback.format_exc())
        sys.exit(2)
```

---

## Phase 9: Manual Testing & Iteration

### Step 9.1: First run

Run the pipeline manually:

```bash
python run_digest.py
```

### Step 9.2: Verify outputs

Check that these files were created:
- `data/artifacts/raw_feed_*.xml` — the raw RSS XML
- `data/artifacts/parsed_posts_*.json` — parsed post dicts
- `data/artifacts/enriched_posts_*.json` — posts with scores/comments/flair
- `data/artifacts/filtered_posts_*.json` — filtered posts
- `data/artifacts/posts_with_comments_*.json` — posts with top comments
- `data/digests/digest_*.html` — the final digest
- `data/digests/latest.html` — symlink/copy of latest digest
- `data/seen_ids.json` — updated seen IDs
- `logs/run_*.log` — log file with full pipeline trace
- `CLAUDE.md` — updated with run metrics

### Step 9.3: Open the digest

Open `data/digests/latest.html` in a browser. Verify:
- Title and date are correct.
- Posts are listed with titles, scores, comment counts, authors.
- Comments appear under each post with author, score, and body text.
- Mobile-responsive: resize browser to 375px width and confirm layout works.
- No JavaScript errors in console.

### Step 9.4: Run 3-5 times

Run the pipeline 3-5 more times over the course of a day or two. Verify:
- Deduplication works (second run should have fewer posts).
- `seen_ids.json` grows and caps at 200 entries.
- `CLAUDE.md` run history accumulates entries.
- Logs capture all steps clearly.

### Step 9.5: Test failure modes

Simulate failures to verify graceful degradation:

1. **RSS failure:** Temporarily change `RSS_URL` to an invalid URL. Run pipeline. Verify fallback digest is generated.
2. **API rate limit:** Temporarily set `time.sleep(0)` in the enrichment step and run with many posts. Observe if 429 responses are handled gracefully.
3. **Corrupt seen_ids.json:** Write invalid JSON to `data/seen_ids.json`. Run pipeline. Verify it logs a warning and continues with empty seen list.
4. **Missing templates dir:** Rename `templates/` temporarily. Run pipeline. Verify `render_fallback_digest` produces output.

### Step 9.6: Tune filters

After reviewing 3-5 digests manually:
- Are threads you'd want to read making it through? If not, loosen filters.
- Are promotional/noise threads getting in? If so, add keywords to `EXCLUDED_KEYWORDS`.
- Is the comment quality good? Adjust `MAX_COMMENTS_PER_POST` or the 500-char truncation limit.
- Is the comment-to-score ratio filter too aggressive? Adjust `MIN_COMMENT_SCORE_RATIO`.

---

## Phase 10: VPS Deployment

### Step 10.1: Provision a VPS

1. Create a DigitalOcean or Linode VPS:
   - **Size:** Smallest available ($5/month, 1GB RAM, 1 vCPU)
   - **OS:** Ubuntu 22.04 LTS
   - **Region:** US East (closest to Reddit servers, matches EST timezone)
2. Set up SSH key access. Do not use password auth.

### Step 10.2: Server setup

SSH into the VPS and run:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git
sudo timedatectl set-timezone America/New_York
```

### Step 10.3: Deploy the project

```bash
mkdir -p /opt/tv-signal
cd /opt/tv-signal
git clone <your-repo-url> .
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Step 10.4: Set up the cron job

```bash
crontab -e
```

Add this line:

```
0 23 * * * cd /opt/tv-signal && /opt/tv-signal/venv/bin/python run_digest.py >> /opt/tv-signal/logs/cron.log 2>&1
```

This runs the pipeline every day at 11:00 PM EST (server is set to EST timezone).

### Step 10.5: Set up CLAUDE.md backup cron

```bash
crontab -e
```

Add this line:

```
0 */6 * * * cd /opt/tv-signal && git add CLAUDE.md data/seen_ids.json && git commit -m "auto: state backup $(date +\%Y\%m\%d_\%H\%M)" --allow-empty && git push origin main
```

This pushes state to GitHub every 6 hours.

### Step 10.6: Set up health check and auto-restart

Create `/opt/tv-signal/healthcheck.sh`:

```bash
#!/bin/bash
# Check if latest digest was generated within last 26 hours
DIGEST="/opt/tv-signal/data/digests/latest.html"
if [ ! -f "$DIGEST" ]; then
    echo "$(date) WARN: No digest file found" >> /opt/tv-signal/logs/health.log
    exit 1
fi

AGE=$(( $(date +%s) - $(stat -c %Y "$DIGEST") ))
if [ "$AGE" -gt 93600 ]; then
    echo "$(date) WARN: Digest is $(($AGE / 3600)) hours old" >> /opt/tv-signal/logs/health.log
    exit 1
fi

echo "$(date) OK: Digest is $(($AGE / 3600)) hours old" >> /opt/tv-signal/logs/health.log
exit 0
```

```bash
chmod +x /opt/tv-signal/healthcheck.sh
```

Add to crontab:

```
30 7 * * * /opt/tv-signal/healthcheck.sh
```

This runs at 7:30 AM daily (8.5 hours after digest generation) and logs health status.

### Step 10.7: Verify deployment

1. Run `python run_digest.py` manually on the VPS.
2. Check output files exist as expected.
3. Wait for the 11 PM cron to trigger and verify the log file the next morning.
4. Check `CLAUDE.md` backup is being pushed to GitHub.

---

## Phase 11: Git Repository & README

### Step 11.1: Initialize git repo

```bash
cd /path/to/tv-signal
git init
git add .
git commit -m "initial: TV Signal MVP — 7-task RSS digest pipeline"
```

### Step 11.2: Create README.md

Write a README with:

1. **One-line description:** "Daily curated digest of high-engagement TV discussion threads from Reddit."
2. **What it does:** 3 bullet points — fetches /r/television, filters for discussion threads (>50 comments, excludes trailers/casting), generates mobile-friendly HTML digest with top comments.
3. **Quick start:** `pip install -r requirements.txt && python run_digest.py && open data/digests/latest.html`
4. **How it works:** List the 7 pipeline tasks with one sentence each.
5. **Configuration:** Document the hardcoded constants and where to find them (`MIN_COMMENTS` in `pipeline/filter_posts.py`, etc.).
6. **Self-hosting:** Instructions for setting up the cron job.
7. **License:** MIT.

Do NOT over-write the README. Keep it under 100 lines. Let the code speak for itself.

### Step 11.3: Push to GitHub

```bash
git remote add origin <your-repo-url>
git push -u origin main
```

---

## Summary: File-by-File Reference

| File | Purpose | Input | Output |
|---|---|---|---|
| `run_digest.py` | Orchestrator, runs all 7 tasks serially | None | Metrics dict, digest file |
| `pipeline/fetch_rss.py` | Downloads RSS XML from Reddit | None | Raw XML string |
| `pipeline/parse_posts.py` | Parses XML into post dicts | XML string | List of post dicts |
| `pipeline/deduplicate.py` | Removes previously seen posts | Post list | Filtered post list |
| `pipeline/filter_posts.py` | Enriches via API + applies filters | Post list | Filtered post list |
| `pipeline/extract_comments.py` | Fetches top comments per post | Post list | Post list with comments |
| `pipeline/render_html.py` | Generates HTML digest file | Post list | File path string |
| `pipeline/update_memory.py` | Persists seen IDs and metrics | Post list + metrics | None (writes files) |
| `templates/digest.html` | Jinja2 HTML template | Template vars | Rendered HTML |
| `data/seen_ids.json` | Rolling window of 200 seen post IDs | — | — |
| `CLAUDE.md` | Project memory: last run, run history | — | — |

## Critical Rules

1. **Never crash silently.** Every exception must be logged. Users must always get a digest file, even if it's a fallback.
2. **Rate limit Reddit.** Always `time.sleep(1.0)` between Reddit API requests. Never remove this.
3. **Never lose state.** `seen_ids.json` and `CLAUDE.md` must survive crashes. Back up to git.
4. **Keep it simple.** No config files, no databases, no environment variables for MVP. Constants live in the Python files.
5. **Artifacts are disposable.** Everything in `data/artifacts/` is debug output. It can be deleted anytime without affecting the pipeline.
6. **`latest.html` is the product.** This file is what users consume. It must always be valid HTML.

---

## Phase 12: Feature Expansion (16 Features)

This phase adds 16 features to the digest. Features are grouped into 4 batches. Build them in order. All interactive features use vanilla JavaScript + localStorage. No frameworks, no build step, no external dependencies.

### Design Decisions (from interview)

- **Aesthetic:** Dark mode, modern. Background `#0d1117`, glassmorphism cards with `backdrop-filter: blur(10px)`, bright accent colors.
- **Tech stack:** Vanilla JS + localStorage. No frameworks.
- **Sentiment/consensus:** Simple hardcoded keyword lists. No weighted scoring, no negation handling.
- **Creator detection:** Flair/keyword matching only. No curated name list.
- **Show name extraction:** Python extracts at build time, embeds as `data-show-name` attributes. JS reads them.
- **Conversation catalyst:** Use top-voted comment (highest `score`). No extra API calls for reply trees.
- **Scope:** 16 features. Cut #10 (Comparison View) and #12 (RSS Feed of Digest).
- **Max width:** Increase from 640px to 720px.

---

### Batch A: Visual Polish (#1, #2, #3, #11, #23)

These features change CSS and HTML structure only. No Python changes needed for this batch.

---

#### Feature #1 — Visual Hierarchy Overhaul

**What it does:** Bigger/bolder titles, colored comment-count badges, better post spacing, GitHub-style flair tags.

##### Step 12.1.1: Update body styles in `templates/digest.html`

Change the `body` CSS rule:
- `color` from `#222` to `#e0e0e0`
- `background` from `#f5f5f5` to `#0d1117`
- `max-width` from `640px` to `720px`

##### Step 12.1.2: Update header styles

- `.header h1`: Change `font-size` to `32px`, `font-weight` to `800`, `color` to `#fff`, add `letter-spacing: -0.5px`.
- `.header`: Change `border-bottom` to `1px solid rgba(255,255,255,0.08)`, add `padding: 32px 0 20px`.
- `.header .date`: Change `color` to `#9ca3af`, add `margin-top: 8px`.

##### Step 12.1.3: Update post card styles

Change `.post` CSS:
- `background` to `rgba(255,255,255,0.04)`
- `border` to `1px solid rgba(255,255,255,0.08)`
- `border-radius` to `14px`
- `padding` to `20px`
- `margin-bottom` to `20px`
- Add `backdrop-filter: blur(10px)`
- Add `transition: border-color 0.2s`
- Add `.post:hover { border-color: rgba(255,255,255,0.15); }`

##### Step 12.1.4: Update post title styles

Change `.post-title`:
- `font-size` to `20px`
- `font-weight` to `700`
- `color` to `#fff`
- `margin-bottom` to `8px`
- Add `line-height: 1.3`
- `.post-title:hover` color to `#a5b4fc`

##### Step 12.1.5: Add colored comment-count badges

Add new CSS class `.badge-comments`:
```css
.badge-comments {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 1px 8px;
  border-radius: 10px;
  font-weight: 600;
  font-size: 12px;
}
.badge-500 { background: rgba(239,68,68,0.2); color: #fca5a5; }
.badge-100 { background: rgba(249,115,22,0.2); color: #fdba74; }
.badge-50  { background: rgba(59,130,246,0.2); color: #93c5fd; }
```

In the post template, replace the plain `💬 {{ post.num_comments }}` span with:
```jinja2
{% if post.num_comments >= 500 %}
<span class="badge-comments badge-500">{{ post.num_comments }}</span>
{% elif post.num_comments >= 100 %}
<span class="badge-comments badge-100">{{ post.num_comments }}</span>
{% else %}
<span class="badge-comments badge-50">{{ post.num_comments }}</span>
{% endif %}
```

##### Step 12.1.6: Restyle flair as GitHub-style tag

Change `.flair` CSS:
```css
.flair {
  display: inline-block;
  background: rgba(99,102,241,0.15);
  color: #a5b4fc;
  padding: 1px 10px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 500;
  border: 1px solid rgba(99,102,241,0.25);
}
```

##### Step 12.1.7: Update post-meta to flexbox layout

Change `.post-meta`:
```css
.post-meta {
  font-size: 13px;
  color: #6b7280;
  margin-bottom: 12px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}
```

Remove the old `.post-meta span { margin-right: 12px; }` rule (gap handles spacing now).

---

#### Feature #2 — Enhanced Comment Previews

**What it does:** Colored left border on comments, subtle background + shadow, truncation to 3 lines with "...", green upvote indicator, "showing X of Y comments" label.

##### Step 12.2.1: Update comment CSS

Replace the `.comment` rule:
```css
.comment {
  padding: 10px 14px;
  border-left: 3px solid rgba(99,102,241,0.4);
  margin-bottom: 10px;
  font-size: 14px;
  background: rgba(255,255,255,0.02);
  border-radius: 0 8px 8px 0;
  box-shadow: 0 1px 3px rgba(0,0,0,0.2);
}
```

##### Step 12.2.2: Update comment-meta CSS

```css
.comment-meta {
  font-size: 12px;
  color: #6b7280;
  margin-bottom: 4px;
  display: flex;
  align-items: center;
  gap: 6px;
}
```

Add a green score class:
```css
.comment-score { color: #86efac; }
```

Update the comment-meta template from:
```
{{ comment.author }} · ▲ {{ comment.score }}
```
to:
```html
<span>{{ comment.author }}</span>
<span class="comment-score">&#9650; {{ comment.score }}</span>
```

##### Step 12.2.3: Add comment body truncation CSS

```css
.comment-body {
  color: #d1d5db;
  word-wrap: break-word;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
```

##### Step 12.2.4: Add "showing X of Y" label

Add CSS:
```css
.comments-count-label {
  font-size: 11px;
  color: #6b7280;
  margin-bottom: 10px;
}
```

In the template, add this line right after `<div class="comments-section">` and before the comment loop:
```jinja2
<div class="comments-count-label">Showing {{ post.comments | length }} of {{ post.num_comments }} comments</div>
```

##### Step 12.2.5: Update comments-section border

```css
.comments-section {
  border-top: 1px solid rgba(255,255,255,0.06);
  padding-top: 14px;
  margin-top: 14px;
}
```

---

#### Feature #3 — Time Context & Freshness

**What it does:** Converts timestamps to "3h ago" / "2d ago", adds pulsing "TRENDING NOW" badge for posts < 6 hours old with 200+ comments, shows "Last updated" in header.

##### Step 12.3.1: Add freshness computation in `pipeline/render_html.py`

In the `_enrich_posts_for_template()` function (or create this function if it doesn't exist), add this block for each post:

```python
import datetime

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
```

##### Step 12.3.2: Add time_ago to post-meta in template

After the `by {{ post.author }}` span, add:
```jinja2
{% if post.time_ago %}
<span>{{ post.time_ago }}</span>
{% endif %}
```

##### Step 12.3.3: Add trending badge HTML

Inside the `.post` div, before the post title, add:
```jinja2
{% if post.is_trending %}
<div class="trending-badge">TRENDING NOW</div>
{% endif %}
```

##### Step 12.3.4: Add trending badge CSS

```css
.trending-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: rgba(239,68,68,0.15);
  border: 1px solid rgba(239,68,68,0.3);
  color: #fca5a5;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 10px;
  border-radius: 12px;
  animation: pulse-badge 2s infinite;
  margin-bottom: 8px;
}
@keyframes pulse-badge {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}
```

##### Step 12.3.5: Add "Last updated" to header

Add a new div in the header section, after the date div:
```html
<div class="last-updated">Last updated {{ generated_at }}</div>
```

Add CSS:
```css
.header .last-updated {
  font-size: 11px;
  color: #6b7280;
  margin-top: 2px;
}
```

---

#### Feature #11 — Social Proof Elements

**What it does:** Tagline under title, footer with next digest time.

##### Step 12.11.1: Add tagline to header

After the `<h1>The TV Signal</h1>` line, add:
```html
<div class="tagline">Cutting through Reddit's noise since January 2026</div>
```

Add CSS:
```css
.header .tagline {
  font-size: 12px;
  color: #6b7280;
  margin-top: 4px;
  font-style: italic;
}
```

##### Step 12.11.2: Update footer

Replace the footer content with:
```html
<div class="footer">
  <div>Generated by <a href="#">The TV Signal</a> &middot; {{ generated_at }}</div>
  <div class="social-proof">Next digest: Tomorrow at 11 PM EST</div>
</div>
```

Add CSS:
```css
.footer {
  text-align: center;
  padding: 28px 0 16px;
  font-size: 12px;
  color: #4b5563;
  border-top: 1px solid rgba(255,255,255,0.06);
  margin-top: 8px;
}
.footer a { color: #6b7280; text-decoration: none; }
.footer a:hover { color: #9ca3af; }
.footer .social-proof {
  font-size: 11px;
  color: #4b5563;
  margin-top: 8px;
}
```

---

#### Feature #23 — Reading Time Estimates

**What it does:** Shows "X min read" per post based on word count / 200 wpm.

##### Step 12.23.1: Add reading time computation in `pipeline/render_html.py`

Add this function:
```python
import math

def _reading_time(post):
    words = len(post.get("title", "").split())
    for c in post.get("comments", []):
        words += len(c.get("body", "").split())
    return max(1, math.ceil(words / 200))
```

Call it in the enrichment loop:
```python
post["reading_time"] = _reading_time(post)
```

##### Step 12.23.2: Add reading time to post-meta in template

After the flair span, add:
```jinja2
<span class="reading-time">{{ post.reading_time }} min read</span>
```

Add CSS:
```css
.reading-time {
  font-size: 11px;
  color: #6b7280;
}
```

---

### Batch B: Data Intelligence (#6, #7, #19, #26, #33, #34)

These features require Python-side computation in `render_html.py` and new template variables.

---

#### Feature #6 — Digest Stats Dashboard

**What it does:** Summary box at top showing: discussion count, total comments, filtered noise count, hottest thread.

##### Step 12.6.1: Modify `render()` signature in `pipeline/render_html.py`

Change `render(posts: list[dict])` to `render(posts: list[dict], metrics: dict | None = None)`.

##### Step 12.6.2: Compute stats in `render()`

After enriching posts, compute:
```python
total_comments = sum(p.get("num_comments", 0) for p in posts)
hottest = max(posts, key=lambda p: p.get("num_comments", 0)) if posts else None

m = metrics or {}
posts_fetched = m.get("posts_fetched", 0)
posts_filtered_out = posts_fetched - len(posts) if posts_fetched else 0
```

##### Step 12.6.3: Pass new variables to template

Add to the `template.render()` call:
```python
total_comments=total_comments,
hottest_title=hottest["title"] if hottest else "",
hottest_comments=hottest.get("num_comments", 0) if hottest else 0,
posts_filtered_out=posts_filtered_out,
posts_fetched=posts_fetched,
```

##### Step 12.6.4: Update `run_digest.py` to pass metrics

Change the render call in step 8.8 from:
```python
digest_path = render(posts)
```
to:
```python
digest_path = render(posts, metrics=metrics)
```

##### Step 12.6.5: Add stats dashboard HTML to template

Place this block after the `{% endif %}` for degraded notice and before the post loop:

```jinja2
{% if posts | length > 0 %}
<div class="stats-dashboard">
  <h3>Today's Digest</h3>
  <div class="stats-grid">
    <div class="stat-item">
      <div class="stat-value">{{ posts | length }}</div>
      <div class="stat-label">Discussions found</div>
    </div>
    <div class="stat-item">
      <div class="stat-value">{{ "{:,}".format(total_comments) }}</div>
      <div class="stat-label">Total comments</div>
    </div>
    {% if posts_filtered_out > 0 %}
    <div class="stat-item">
      <div class="stat-value">{{ posts_filtered_out }}</div>
      <div class="stat-label">Noise posts filtered</div>
    </div>
    {% endif %}
    {% if hottest_title %}
    <div class="stat-hottest">
      Hottest: <strong>{{ hottest_title | truncate(50) }}</strong> ({{ "{:,}".format(hottest_comments) }} comments)
    </div>
    {% endif %}
  </div>
</div>
{% endif %}
```

##### Step 12.6.6: Add stats dashboard CSS

```css
.stats-dashboard {
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 12px;
  padding: 16px 20px;
  margin-bottom: 24px;
  backdrop-filter: blur(10px);
}
.stats-dashboard h3 {
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: #6b7280;
  margin-bottom: 12px;
}
.stats-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}
.stat-item {
  background: rgba(255,255,255,0.03);
  border-radius: 8px;
  padding: 10px 12px;
}
.stat-value {
  font-size: 22px;
  font-weight: 700;
  color: #fff;
}
.stat-label {
  font-size: 11px;
  color: #6b7280;
  margin-top: 2px;
}
.stat-hottest {
  grid-column: 1 / -1;
  font-size: 12px;
  color: #9ca3af;
  padding: 8px 12px;
  background: rgba(255,255,255,0.03);
  border-radius: 8px;
}
.stat-hottest strong { color: #f59e0b; }
```

---

#### Feature #7 — Sentiment Indicators

**What it does:** Analyzes comment text for positive/negative/mixed keywords. Shows colored badge per post.

##### Step 12.7.1: Add keyword lists to `pipeline/render_html.py`

At module top, define:
```python
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
```

##### Step 12.7.2: Implement `_compute_sentiment()` function

```python
import re

def _compute_sentiment(comments):
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
```

##### Step 12.7.3: Call in enrichment loop

```python
post["sentiment"] = _compute_sentiment(post.get("comments", []))
```

##### Step 12.7.4: Add sentiment badge to post-meta in template

After the flair span:
```jinja2
<span class="sentiment-badge sentiment-{{ post.sentiment.css }}">{{ post.sentiment.emoji }} {{ post.sentiment.label }}</span>
```

##### Step 12.7.5: Add sentiment CSS

```css
.sentiment-badge {
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 10px;
  font-weight: 500;
}
.sentiment-positive { background: rgba(34,197,94,0.15); color: #86efac; }
.sentiment-negative { background: rgba(239,68,68,0.15); color: #fca5a5; }
.sentiment-mixed    { background: rgba(249,115,22,0.15); color: #fdba74; }
.sentiment-neutral  { background: rgba(107,114,128,0.15); color: #9ca3af; }
```

---

#### Feature #19 — Conversation Starter Extraction

**What it does:** Highlights the top-voted comment with gold border and "Conversation Catalyst" label.

##### Step 12.19.1: Mark catalyst comment in enrichment loop

In `_enrich_posts_for_template()`, after processing comments:
```python
comments = post.get("comments", [])
if comments:
    top = max(comments, key=lambda c: c.get("score", 0))
    top["is_catalyst"] = True
```

This mutates the comment dict in-place. Only one comment per post gets flagged.

##### Step 12.19.2: Add catalyst HTML to comment template

Inside the comment div, before the comment-meta div:
```jinja2
{% if comment.is_catalyst is defined and comment.is_catalyst %}
<div class="catalyst-label">Conversation Catalyst</div>
{% endif %}
```

Add the catalyst CSS class to the comment div:
```jinja2
<div class="comment{% if comment.is_catalyst is defined and comment.is_catalyst %} catalyst{% endif %}">
```

##### Step 12.19.3: Add catalyst CSS

```css
.comment.catalyst {
  border-left-color: #fbbf24;
  background: rgba(251,191,36,0.04);
}
.catalyst-label {
  font-size: 11px;
  font-weight: 600;
  color: #fbbf24;
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 4px;
}
```

---

#### Feature #26 — Consensus Detector

**What it does:** Detects agreement vs disagreement in comments. Shows green "Strong Consensus" or orange "Divided Community" badge.

##### Step 12.26.1: Implement `_compute_consensus()` in `pipeline/render_html.py`

```python
def _compute_consensus(comments):
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
```

##### Step 12.26.2: Call in enrichment loop

```python
post["consensus"] = _compute_consensus(post.get("comments", []))
```

Returns `None` when not enough data. Template checks for this.

##### Step 12.26.3: Add consensus badge to post-meta in template

After the sentiment badge:
```jinja2
{% if post.consensus %}
<span class="consensus-badge consensus-{{ post.consensus.css }}">{{ post.consensus.emoji }} {{ post.consensus.label }}</span>
{% endif %}
```

##### Step 12.26.4: Add consensus CSS

```css
.consensus-badge {
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 10px;
  font-weight: 500;
}
.consensus-consensus { background: rgba(34,197,94,0.15); color: #86efac; }
.consensus-divided   { background: rgba(249,115,22,0.15); color: #fdba74; }
```

---

#### Feature #33 — Digest Impact Metrics

**What it does:** Footer line showing total comments covered and noise filtered.

##### Step 12.33.1: Add impact line to footer in template

Before the "Generated by" line in the footer:
```jinja2
{% if total_comments > 0 %}
<div class="impact">
  This digest covers {{ "{:,}".format(total_comments) }} comments{% if posts_filtered_out > 0 %} &middot; filtered out {{ posts_filtered_out }} noise posts{% endif %}
</div>
{% endif %}
```

The `total_comments` and `posts_filtered_out` variables are already passed from Feature #6. No new Python code needed.

##### Step 12.33.2: Add impact CSS

```css
.footer .impact {
  font-size: 11px;
  color: #4b5563;
  margin-bottom: 12px;
  line-height: 1.6;
}
```

---

#### Feature #34 — Creator Callouts

**What it does:** Detects comments by show creators/actors/verified industry people via flair keywords. Highlights with purple border and "Creator Alert" banner.

##### Step 12.34.1: Modify `pipeline/extract_comments.py` to capture author flair

In the comment extraction loop, where each comment dict is created, add `author_flair`:
```python
raw_comments.append({
    "author": c_data.get("author", "[deleted]"),
    "body": body,
    "score": c_data.get("score", 0),
    "author_flair": c_data.get("author_flair_text", "") or "",
})
```

##### Step 12.34.2: Add creator detection keywords to `pipeline/render_html.py`

```python
CREATOR_FLAIR_KEYWORDS = {
    "creator", "showrunner", "writer", "director", "producer", "actor",
    "actress", "verified", "official", "staff", "crew", "show creator",
}
```

##### Step 12.34.3: Implement `_is_creator_comment()` function

```python
def _is_creator_comment(comment):
    flair = comment.get("author_flair", "").lower()
    if not flair:
        return False
    return any(kw in flair for kw in CREATOR_FLAIR_KEYWORDS)
```

##### Step 12.34.4: Call in enrichment loop

For each comment in each post:
```python
for c in post.get("comments", []):
    c["is_creator"] = _is_creator_comment(c)
```

##### Step 12.34.5: Add creator HTML to comment template

Inside the comment div, before comment-meta:
```jinja2
{% if comment.is_creator is defined and comment.is_creator %}
<div class="creator-label">Creator Alert</div>
{% endif %}
```

Add creator class to comment div:
```jinja2
<div class="comment{% if comment.is_creator is defined and comment.is_creator %} creator{% endif %}">
```

##### Step 12.34.6: Add creator CSS

```css
.comment.creator {
  border-left-color: #a855f7;
  background: rgba(168,85,247,0.06);
}
.creator-label {
  font-size: 11px;
  font-weight: 600;
  color: #a855f7;
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 4px;
}
```

---

### Batch C: Personalization (#4, #22, #24, #36)

These features add interactive JavaScript. All state goes in localStorage under keys prefixed `tvs_`.

---

#### Feature #4 — Smart Filtering UI (In-Page)

**What it does:** Checkbox-style buttons at top to filter posts by flair. Instant client-side filtering. Saved to localStorage.

##### Step 12.4.1: Add data-flair attribute to each post div

On the `.post` div, add:
```jinja2
data-flair="{{ post.flair | lower }}"
```

##### Step 12.4.2: Add filter bar HTML

Place this block after the stats dashboard and before the post loop:
```html
<div class="controls">
  <div class="controls-section" id="flair-filters">
    <span class="controls-label">Filter:</span>
    <button class="filter-btn active" data-flair="all" onclick="filterByFlair('all')">All</button>
  </div>
</div>
```

The individual flair buttons are generated dynamically by JavaScript on page load (see Step 12.4.4).

##### Step 12.4.3: Add filter CSS

```css
.controls {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 20px;
  align-items: center;
}
.controls-section {
  display: flex;
  gap: 6px;
  align-items: center;
  flex-wrap: wrap;
}
.controls-label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: #6b7280;
  margin-right: 4px;
}
.filter-btn {
  background: rgba(255,255,255,0.06);
  border: 1px solid rgba(255,255,255,0.1);
  color: #9ca3af;
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}
.filter-btn:hover {
  background: rgba(255,255,255,0.1);
  color: #e0e0e0;
}
.filter-btn.active {
  background: rgba(99,102,241,0.2);
  border-color: rgba(99,102,241,0.4);
  color: #a5b4fc;
}
```

##### Step 12.4.4: Add filter JavaScript

Add a `<script>` block at the bottom of `<body>`. Start with localStorage helpers:

```javascript
function getLS(key, def) {
  try { var v = localStorage.getItem('tvs_' + key); return v ? JSON.parse(v) : def; }
  catch(e) { return def; }
}
function setLS(key, val) {
  try { localStorage.setItem('tvs_' + key, JSON.stringify(val)); } catch(e) {}
}
```

Then the flair filter IIFE:
```javascript
(function initFlairFilters() {
  var flairs = new Set();
  document.querySelectorAll('.post[data-flair]').forEach(function(p) {
    var f = p.getAttribute('data-flair');
    if (f) flairs.add(f);
  });
  var container = document.getElementById('flair-filters');
  flairs.forEach(function(f) {
    var btn = document.createElement('button');
    btn.className = 'filter-btn';
    btn.setAttribute('data-flair', f);
    btn.textContent = f.charAt(0).toUpperCase() + f.slice(1);
    btn.onclick = function() { filterByFlair(f); };
    container.appendChild(btn);
  });
  var saved = getLS('flair_filter', 'all');
  if (saved !== 'all') filterByFlair(saved);
})();

function filterByFlair(flair) {
  document.querySelectorAll('.filter-btn').forEach(function(b) {
    b.classList.toggle('active', b.getAttribute('data-flair') === flair);
  });
  document.querySelectorAll('.post[data-flair]').forEach(function(p) {
    if (flair === 'all' || p.getAttribute('data-flair') === flair) {
      p.style.display = '';
    } else {
      p.style.display = 'none';
    }
  });
  setLS('flair_filter', flair);
}
```

---

#### Feature #22 — "My Shows" Tracking

**What it does:** Extracts show names from titles (Python-side), adds "Track" button, shows tracked shows panel at top, highlights tracked posts with gold border.

##### Step 12.22.1: Add show name extraction in `pipeline/render_html.py`

```python
def _extract_show_name(title):
    # Pattern: "Show Name S01E02"
    m = re.match(r"^(.+?)\s+S\d{1,2}E\d{1,2}", title, re.IGNORECASE)
    if m:
        return m.group(1).strip().strip('"').strip("'")
    # Pattern: "Show Name - Season 1"
    m = re.match(r"^(.+?)\s*[-\u2013\u2014]\s*(?:Season|Series)\s+\d", title, re.IGNORECASE)
    if m:
        return m.group(1).strip().strip('"').strip("'")
    # Pattern: quoted show name at start
    m = re.match(r'^["\'](.+?)["\']', title)
    if m:
        return m.group(1).strip()
    return ""
```

Call in enrichment:
```python
post["show_name"] = _extract_show_name(post.get("title", ""))
```

##### Step 12.22.2: Add data-show-name attribute to post div

```jinja2
data-show-name="{{ post.show_name }}"
```

##### Step 12.22.3: Add Track button to post actions

Only show if show name was extracted:
```jinja2
{% if post.show_name %}
<button class="action-btn track-btn" data-show="{{ post.show_name }}" onclick="toggleTrack(this, '{{ post.show_name }}')">&#9734; Track</button>
{% endif %}
```

##### Step 12.22.4: Add My Shows panel HTML

Place before the post loop:
```html
<div class="my-shows-panel" id="my-shows-panel">
  <h3>My Shows</h3>
  <div class="my-shows-list" id="my-shows-list"></div>
</div>
```

##### Step 12.22.5: Add My Shows CSS

```css
.my-shows-panel {
  background: rgba(251,191,36,0.06);
  border: 1px solid rgba(251,191,36,0.15);
  border-radius: 12px;
  padding: 14px 18px;
  margin-bottom: 20px;
  display: none;
}
.my-shows-panel.visible { display: block; }
.my-shows-panel h3 {
  font-size: 13px;
  color: #fbbf24;
  margin-bottom: 8px;
}
.my-shows-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.my-show-tag {
  background: rgba(251,191,36,0.12);
  border: 1px solid rgba(251,191,36,0.2);
  color: #fbbf24;
  padding: 2px 10px;
  border-radius: 12px;
  font-size: 12px;
  cursor: pointer;
}
.my-show-tag:hover { background: rgba(251,191,36,0.2); }
.post.tracked-show { border-left: 3px solid #fbbf24; }
.track-btn.active { color: #fbbf24; border-color: rgba(251,191,36,0.3); }
```

##### Step 12.22.6: Add tracking JavaScript

```javascript
(function initShows() {
  var tracked = getLS('tracked_shows', []);
  refreshShowsPanel(tracked);
  document.querySelectorAll('.post[data-show-name]').forEach(function(p) {
    var show = p.getAttribute('data-show-name');
    if (show && tracked.indexOf(show) > -1) {
      p.classList.add('tracked-show');
      var btn = p.querySelector('.track-btn');
      if (btn) { btn.classList.add('active'); btn.innerHTML = '&#9733; Tracked'; }
    }
  });
})();

function toggleTrack(btn, show) {
  var tracked = getLS('tracked_shows', []);
  var idx = tracked.indexOf(show);
  if (idx > -1) {
    tracked.splice(idx, 1);
    btn.classList.remove('active');
    btn.innerHTML = '&#9734; Track';
    btn.closest('.post').classList.remove('tracked-show');
  } else {
    tracked.push(show);
    btn.classList.add('active');
    btn.innerHTML = '&#9733; Tracked';
    btn.closest('.post').classList.add('tracked-show');
  }
  setLS('tracked_shows', tracked);
  refreshShowsPanel(tracked);
}

function refreshShowsPanel(tracked) {
  var panel = document.getElementById('my-shows-panel');
  var list = document.getElementById('my-shows-list');
  if (tracked.length === 0) { panel.classList.remove('visible'); return; }
  panel.classList.add('visible');
  list.innerHTML = '';
  tracked.forEach(function(s) {
    var tag = document.createElement('span');
    tag.className = 'my-show-tag';
    tag.textContent = s;
    tag.onclick = function() { toggleTrack(null, s); refreshShowsPanel(getLS('tracked_shows', [])); };
    list.appendChild(tag);
  });
}
```

---

#### Feature #24 — Digest Difficulty Levels

**What it does:** Three reading modes: Quick Hits (1 comment, 2-line clamp), Standard (default), Deep Dive (all comments, no clamp). Toggle buttons in controls bar.

##### Step 12.24.1: Add mode buttons to controls bar

Inside the `.controls` div, add a second section:
```html
<div class="controls-section">
  <span class="controls-label">Mode:</span>
  <button class="mode-btn" data-mode="quick" onclick="setMode('quick')">Quick Hits</button>
  <button class="mode-btn active" data-mode="standard" onclick="setMode('standard')">Standard</button>
  <button class="mode-btn" data-mode="deep" onclick="setMode('deep')">Deep Dive</button>
</div>
```

##### Step 12.24.2: Add mode-btn CSS

Use the same styles as `.filter-btn`:
```css
.mode-btn {
  background: rgba(255,255,255,0.06);
  border: 1px solid rgba(255,255,255,0.1);
  color: #9ca3af;
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}
.mode-btn:hover {
  background: rgba(255,255,255,0.1);
  color: #e0e0e0;
}
.mode-btn.active {
  background: rgba(99,102,241,0.2);
  border-color: rgba(99,102,241,0.4);
  color: #a5b4fc;
}
```

##### Step 12.24.3: Add mode CSS rules

These rules apply globally when the body has a mode class:
```css
.mode-quick .comment:nth-child(n+2) { display: none; }
.mode-quick .comment-body { -webkit-line-clamp: 2; }
.mode-deep .comment-body { -webkit-line-clamp: unset; overflow: visible; }
```

`mode-standard` uses the default 3-line clamp from Feature #2. No extra CSS needed.

##### Step 12.24.4: Add mode JavaScript

```javascript
(function initMode() {
  var saved = getLS('read_mode', 'standard');
  setMode(saved);
})();

function setMode(mode) {
  document.querySelectorAll('.mode-btn').forEach(function(b) {
    b.classList.toggle('active', b.getAttribute('data-mode') === mode);
  });
  document.body.classList.remove('mode-quick', 'mode-standard', 'mode-deep');
  document.body.classList.add('mode-' + mode);
  setLS('read_mode', mode);
}
```

---

#### Feature #36 — Discussion Bookmarks

**What it does:** "Save" button per post, bookmarks panel at top, export to CSV, persists in localStorage.

##### Step 12.36.1: Add data attributes to post div

The post div needs `data-post-id`, `data-title`, and `data-url`:
```jinja2
data-post-id="{{ post.id }}"
data-title="{{ post.title }}"
data-url="{{ post.url }}"
```

##### Step 12.36.2: Add bookmark button to post actions

```jinja2
<button class="action-btn bookmark-btn" onclick="toggleBookmark(this, '{{ post.id }}', decodeURIComponent('{{ post.title | urlencode }}'), '{{ post.url }}')">&#128278; Save</button>
```

Note: Use `urlencode` filter to safely embed the title, then `decodeURIComponent()` in JS to restore it. This avoids quote-escaping issues.

##### Step 12.36.3: Add bookmarks panel HTML

Place after the My Shows panel:
```html
<div class="bookmarks-panel" id="bookmarks-panel">
  <h3>
    <span>Bookmarks</span>
    <button class="bookmark-export-btn" onclick="exportBookmarks()">Export CSV</button>
  </h3>
  <div class="bookmarks-list" id="bookmarks-list"></div>
</div>
```

##### Step 12.36.4: Add bookmarks CSS

```css
.bookmarks-panel {
  background: rgba(99,102,241,0.06);
  border: 1px solid rgba(99,102,241,0.15);
  border-radius: 12px;
  padding: 14px 18px;
  margin-bottom: 20px;
  display: none;
}
.bookmarks-panel.visible { display: block; }
.bookmarks-panel h3 {
  font-size: 13px;
  color: #a5b4fc;
  margin-bottom: 8px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.bookmark-export-btn {
  font-size: 11px;
  background: rgba(99,102,241,0.15);
  border: 1px solid rgba(99,102,241,0.3);
  color: #a5b4fc;
  padding: 2px 10px;
  border-radius: 10px;
  cursor: pointer;
}
.bookmarks-list { font-size: 13px; }
.bookmarks-list a {
  color: #a5b4fc;
  text-decoration: none;
  display: block;
  padding: 4px 0;
}
.bookmarks-list a:hover { color: #c4b5fd; }
```

##### Step 12.36.5: Add bookmark JavaScript

```javascript
(function initBookmarks() {
  refreshBookmarksPanel();
  var bookmarks = getLS('bookmarks', {});
  Object.keys(bookmarks).forEach(function(id) {
    var el = document.getElementById('post-' + id);
    if (el) {
      var btn = el.querySelector('.bookmark-btn');
      if (btn) btn.classList.add('active');
    }
  });
})();

function toggleBookmark(btn, id, title, url) {
  var bookmarks = getLS('bookmarks', {});
  if (bookmarks[id]) {
    delete bookmarks[id];
    if (btn) btn.classList.remove('active');
  } else {
    bookmarks[id] = { title: title, url: url };
    if (btn) btn.classList.add('active');
  }
  setLS('bookmarks', bookmarks);
  refreshBookmarksPanel();
}

function refreshBookmarksPanel() {
  var bookmarks = getLS('bookmarks', {});
  var keys = Object.keys(bookmarks);
  var panel = document.getElementById('bookmarks-panel');
  var list = document.getElementById('bookmarks-list');
  if (keys.length === 0) { panel.classList.remove('visible'); return; }
  panel.classList.add('visible');
  list.innerHTML = '';
  keys.forEach(function(id) {
    var a = document.createElement('a');
    a.href = bookmarks[id].url;
    a.target = '_blank';
    a.textContent = bookmarks[id].title;
    list.appendChild(a);
  });
}

function exportBookmarks() {
  var bookmarks = getLS('bookmarks', {});
  var csv = 'Title,URL\n';
  Object.keys(bookmarks).forEach(function(id) {
    csv += '"' + bookmarks[id].title.replace(/"/g, '""') + '","' + bookmarks[id].url + '"\n';
  });
  var blob = new Blob([csv], { type: 'text/csv' });
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'tv_signal_bookmarks.csv';
  a.click();
}
```

---

### Batch D: User Actions (#8, #20)

---

#### Feature #8 — One-Click Actions

**What it does:** Three buttons per post: Mark as Read (grays out + strikethrough), Hide (removes from view), Share (copy link). All states saved to localStorage.

##### Step 12.8.1: Add post ID to div

The post div must have `id="post-{{ post.id }}"` for JavaScript targeting.

##### Step 12.8.2: Add action buttons HTML

Inside each `.post` div, after the comments section and spoiler-content wrapper, add:
```jinja2
<div class="post-actions">
  <button class="action-btn mark-read-btn" onclick="markRead(this, '{{ post.id }}')">&#10003; Read</button>
  <button class="action-btn hide-btn" onclick="hidePost(this, '{{ post.id }}')">&#10005; Hide</button>
  <button class="action-btn share-btn" onclick="sharePost('{{ post.url }}')">&#128279; Share</button>
</div>
```

##### Step 12.8.3: Add action button CSS

```css
.post-actions {
  display: flex;
  gap: 6px;
  margin-top: 12px;
}
.action-btn {
  background: rgba(255,255,255,0.05);
  border: 1px solid rgba(255,255,255,0.1);
  color: #6b7280;
  padding: 4px 12px;
  border-radius: 8px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}
.action-btn:hover { background: rgba(255,255,255,0.1); color: #e0e0e0; }
.action-btn.active { color: #a5b4fc; border-color: rgba(99,102,241,0.3); }
```

##### Step 12.8.4: Add read/hidden post CSS

```css
.post.read-post { opacity: 0.45; }
.post.read-post .post-title { text-decoration: line-through; }
.post.hidden-post { display: none; }
```

##### Step 12.8.5: Add Mark as Read JavaScript

```javascript
(function initRead() {
  var read = getLS('read_posts', []);
  read.forEach(function(id) {
    var el = document.getElementById('post-' + id);
    if (el) {
      el.classList.add('read-post');
      var btn = el.querySelector('.mark-read-btn');
      if (btn) btn.classList.add('active');
    }
  });
})();

function markRead(btn, id) {
  var read = getLS('read_posts', []);
  var el = document.getElementById('post-' + id);
  var idx = read.indexOf(id);
  if (idx > -1) {
    read.splice(idx, 1);
    el.classList.remove('read-post');
    btn.classList.remove('active');
  } else {
    read.push(id);
    el.classList.add('read-post');
    btn.classList.add('active');
  }
  setLS('read_posts', read);
}
```

##### Step 12.8.6: Add Hide JavaScript

```javascript
(function initHidden() {
  var hidden = getLS('hidden_posts', []);
  hidden.forEach(function(id) {
    var el = document.getElementById('post-' + id);
    if (el) el.classList.add('hidden-post');
  });
})();

function hidePost(btn, id) {
  var hidden = getLS('hidden_posts', []);
  if (hidden.indexOf(id) === -1) hidden.push(id);
  setLS('hidden_posts', hidden);
  var el = document.getElementById('post-' + id);
  if (el) el.classList.add('hidden-post');
}
```

##### Step 12.8.7: Add Share JavaScript

```javascript
function sharePost(url) {
  if (navigator.share) {
    navigator.share({ url: url });
  } else if (navigator.clipboard) {
    navigator.clipboard.writeText(url);
  }
}
```

Uses native Web Share API on mobile, falls back to clipboard copy on desktop.

---

#### Feature #20 — Spoiler-Safe Summaries

**What it does:** Detects spoiler keywords in title/flair, adds red warning banner, blurs post content by default, checkbox to reveal.

##### Step 12.20.1: Add spoiler detection in `pipeline/render_html.py`

```python
SPOILER_KEYWORDS = {
    "finale", "twist", "dies", "death", "killed", "ending", "spoiler",
    "reveal", "plot twist", "cliffhanger",
}
SPOILER_EPISODE_RE = re.compile(r"S\d{2}E\d{2}", re.IGNORECASE)

def _has_spoiler(post):
    title_lower = post.get("title", "").lower()
    flair_lower = post.get("flair", "").lower()
    if "spoiler" in flair_lower:
        return True
    if SPOILER_EPISODE_RE.search(post.get("title", "")):
        return True
    return any(kw in title_lower for kw in SPOILER_KEYWORDS)
```

Call in enrichment:
```python
post["has_spoiler"] = _has_spoiler(post)
```

##### Step 12.20.2: Add spoiler class to post div

```jinja2
<div class="post{% if post.has_spoiler %} spoiler-post{% endif %}" ...>
```

##### Step 12.20.3: Add spoiler banner HTML

Inside the post div, before the spoiler-content wrapper:
```jinja2
{% if post.has_spoiler %}
<div class="spoiler-banner">
  Warning: Spoilers
  <span class="spoiler-toggle" onclick="toggleSpoiler(this)">Show anyway</span>
</div>
{% endif %}
```

##### Step 12.20.4: Wrap post content in spoiler-content div

Everything between the banner and the action buttons gets wrapped:
```jinja2
<div class="{% if post.has_spoiler %}spoiler-content{% endif %}">
  <!-- title, meta, comments all go here -->
</div>
```

##### Step 12.20.5: Add spoiler CSS

```css
.post.spoiler-post .spoiler-content { filter: blur(6px); transition: filter 0.3s; }
.post.spoiler-post .spoiler-content.revealed { filter: none; }
.spoiler-banner {
  background: rgba(239,68,68,0.15);
  border: 1px solid rgba(239,68,68,0.3);
  color: #fca5a5;
  font-size: 12px;
  font-weight: 600;
  padding: 4px 12px;
  border-radius: 8px;
  margin-bottom: 10px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.spoiler-toggle {
  font-size: 11px;
  color: #9ca3af;
  cursor: pointer;
  margin-left: 8px;
  text-decoration: underline;
}
```

##### Step 12.20.6: Add spoiler toggle JavaScript

```javascript
function toggleSpoiler(el) {
  var content = el.closest('.spoiler-post').querySelector('.spoiler-content');
  content.classList.toggle('revealed');
  el.textContent = content.classList.contains('revealed') ? 'Hide' : 'Show anyway';
}
```

Spoiler state is NOT saved to localStorage. It resets on page load for safety.

---

### Batch E: Enrichment Pipeline Setup

This section describes the structural changes needed in `pipeline/render_html.py` to support all 16 features. All Python computation happens in a single function called before template rendering.

---

#### Step 12.E.1: Create `_enrich_posts_for_template()` function

Add this function to `pipeline/render_html.py`. It is called once in `render()` before passing data to the template. It loops through all posts and computes every feature's data:

```python
def _enrich_posts_for_template(posts):
    total_comments = 0
    for post in posts:
        post["sentiment"] = _compute_sentiment(post.get("comments", []))      # #7
        post["consensus"] = _compute_consensus(post.get("comments", []))      # #26
        post["show_name"] = _extract_show_name(post.get("title", ""))         # #22
        post["reading_time"] = _reading_time(post)                            # #23
        post["has_spoiler"] = _has_spoiler(post)                              # #20

        for c in post.get("comments", []):                                    # #34
            c["is_creator"] = _is_creator_comment(c)

        comments = post.get("comments", [])                                   # #19
        if comments:
            top = max(comments, key=lambda c: c.get("score", 0))
            top["is_catalyst"] = True

        # Freshness (#3)
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
```

#### Step 12.E.2: Call from `render()`

In the `render()` function, before `template.render()`:
```python
posts, total_comments = _enrich_posts_for_template(posts)
```

#### Step 12.E.3: Required imports for `render_html.py`

Make sure these are all imported at the top:
```python
import jinja2
import datetime
import os
import re
import math
import logging
```

---

### Template Assembly Order

When building the full `templates/digest.html`, the sections appear in this order from top to bottom:

1. `<style>` block with all CSS
2. `<body>` starts
3. Header (h1, tagline, date, last-updated)
4. Degraded notice (conditional)
5. Stats dashboard (#6)
6. Controls bar (flair filters #4 + mode buttons #24)
7. My Shows panel (#22)
8. Bookmarks panel (#36)
9. Post loop:
   - Trending badge (#3)
   - Spoiler banner (#20)
   - Spoiler-content wrapper (#20)
   - Post title
   - Post meta (score, badge #1, author, time_ago #3, flair #1, sentiment #7, consensus #26, reading time #23)
   - Comments section (#2) with catalyst #19 and creator #34 labels
   - End spoiler-content wrapper
   - Action buttons (#8 read/hide/share, #22 track, #36 bookmark)
10. Empty state (no posts)
11. Footer (impact #33, generated-by, social proof #11)
12. `<script>` block with all JavaScript

---

### localStorage Keys Reference

All keys are prefixed with `tvs_`:

| Key | Type | Feature | Description |
|-----|------|---------|-------------|
| `tvs_flair_filter` | string | #4 | Currently selected flair filter ("all" or flair name) |
| `tvs_read_mode` | string | #24 | Reading mode ("quick", "standard", "deep") |
| `tvs_read_posts` | string[] | #8 | Array of post IDs marked as read |
| `tvs_hidden_posts` | string[] | #8 | Array of post IDs that are hidden |
| `tvs_tracked_shows` | string[] | #22 | Array of tracked show names |
| `tvs_bookmarks` | object | #36 | Map of post ID → {title, url} |

---

### Files Modified (Summary)

| File | Changes |
|------|---------|
| `pipeline/extract_comments.py` | Add `author_flair` field to comment dict (Step 12.34.1) |
| `pipeline/render_html.py` | Add `_enrich_posts_for_template()` and all helper functions. Change `render()` signature to accept `metrics`. Add new imports: `re`, `math`. (Steps 12.E.1-E.3, plus all feature computation functions) |
| `run_digest.py` | Pass `metrics=metrics` to `render()` call (Step 12.6.4) |
| `templates/digest.html` | Complete rewrite: dark mode CSS, all HTML sections, all JavaScript. (All template steps above) |

No other files are changed. The pipeline structure (7 tasks, serial execution) is unchanged.
