import logging
import os
import sys
import time
import datetime
import json
import traceback

# Task 8.1 Setup logging
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


def _save_metrics(metrics):
    """Helper to save final metrics to an artifact for debugging."""
    os.makedirs("data/artifacts", exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(f"data/artifacts/metrics_{ts}.json", "w") as f:
        json.dump(metrics, f, indent=2)


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

    # Task 1: Fetch
    logger.info("=" * 60)
    logger.info("TASK 1/7: Fetch RSS Feed")
    logger.info("=" * 60)
    try:
        from pipeline.fetch_rss import fetch

        raw_xml = fetch()
    except Exception as e:
        logger.error(f"FATAL: RSS fetch failed: {e}")
        logger.error(traceback.format_exc())
        from pipeline.render_html import render_fallback_digest

        path = render_fallback_digest(f"RSS feed fetch failed: {e}")
        logger.info(f"Fallback digest written to {path}")
        metrics["runtime"] = round(time.time() - start_time, 2)
        metrics["status"] = "failed"
        _save_metrics(metrics)
        return metrics

    # Task 2: Parse
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

    # Task 3: Deduplicate
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

    # Task 4: Filter
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

    # Task 5: Extract Comments
    logger.info("=" * 60)
    logger.info("TASK 5/7: Extract Comments")
    logger.info("=" * 60)
    try:
        from pipeline.extract_comments import extract_comments

        posts = extract_comments(posts)
        metrics["comments_total"] = len(posts)
        metrics["comments_success"] = sum(
            1 for p in posts if p.get("comments") and len(p["comments"]) > 0
        )
        metrics["degraded"] = metrics["comments_success"] == 0 and len(posts) > 0
    except Exception as e:
        logger.warning(f"Comment extraction failed entirely: {e}")
        for p in posts:
            p["comments"] = []
            p["comments_degraded"] = True
        metrics["degraded"] = True

    # Task 6: Render
    logger.info("=" * 60)
    logger.info("TASK 6/7: Render HTML Digest")
    logger.info("=" * 60)
    try:
        from pipeline.render_html import render

        digest_path = render(posts, metrics=metrics)
        metrics["posts_in_digest"] = len(posts)
        logger.info(f"Digest written to {digest_path}")
    except Exception as e:
        logger.error(f"Render failed: {e}")
        logger.error(traceback.format_exc())
        from pipeline.render_html import render_fallback_digest

        digest_path = render_fallback_digest(f"Render failed: {e}")
        metrics["status"] = "failed"

    # Task 7: Update Memory
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

    logger.info("=" * 60)
    logger.info(f"PIPELINE COMPLETE - Status: {metrics['status']}")
    logger.info(f"Runtime: {metrics['runtime']}s")
    logger.info("=" * 60)

    _save_metrics(metrics)
    return metrics


if __name__ == "__main__":
    run_pipeline()
