import requests
import os
import datetime
import logging

RSS_URL = "https://www.reddit.com/r/television/.rss?limit=100"
USER_AGENT = "TheTV Signal/1.0 (RSS digest bot)"
ARTIFACT_DIR = "data/artifacts"

logger = logging.getLogger(__name__)


def fetch() -> str:
    """Fetches RSS feed XML. Returns raw XML string. Raises on failure."""
    os.makedirs(ARTIFACT_DIR, exist_ok=True)

    headers = {"User-Agent": USER_AGENT}

    try:
        logger.info(f"Fetching RSS feed from {RSS_URL}")
        response = requests.get(RSS_URL, headers=headers, timeout=30)

        if response.status_code != 200:
            error_msg = f"Failed to fetch RSS. Status: {response.status_code}. Response: {response.text[:200]}"
            logger.error(error_msg)
            raise Exception(error_msg)

        raw_xml = response.text
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        artifact_path = os.path.join(ARTIFACT_DIR, f"raw_feed_{timestamp}.xml")

        with open(artifact_path, "w", encoding="utf-8") as f:
            f.write(raw_xml)

        logger.info(f"Fetched {len(raw_xml)} bytes and saved to {artifact_path}")
        return raw_xml

    except requests.exceptions.Timeout:
        logger.error("RSS fetch timed out after 30s")
        raise
    except requests.exceptions.ConnectionError:
        logger.error("Cannot reach Reddit RSS")
        raise
    except requests.exceptions.RequestException as e:
        logger.error(f"Generic request error during RSS fetch: {e}")
        raise
