# The TV Signal

Daily curated digest of high-engagement TV discussion threads from Reddit.

## What it does

- **Fetches** /r/television RSS feed daily.
- **Filters** for real discussion threads (>50 comments, excludes trailers, casting, and news).
- **Generates** a premium, mobile-friendly HTML digest with top comments, sentiment analysis, and smart tracking.

## Quick Start

```bash
pip install -r requirements.txt
python run_digest.py
open data/digests/latest.html
```

## How it works

The system uses a 7-task serial pipeline:

1. **Fetch**: Downloads the raw RSS XML from Reddit.
2. **Parse**: Converts XML into structured Python dictionaries.
3. **Deduplicate**: Removes posts seen in the last 200 items.
4. **Enrich & Filter**: Fetches metadata from Reddit JSON API and applies engagement rules.
5. **Extract Comments**: Captures top-voted comments for each filtered post.
6. **Render HTML**: Generates the final responsive dashboard using Jinja2.
7. **Update Memory**: Records run statistics and deduplication state.

## Configuration

Hardcoded constants for easy tuning:

- `MIN_COMMENTS = 50`: Minimum comments to include in digest (`pipeline/filter_posts.py`).
- `MAX_COMMENTS_PER_POST = 3`: Comments shown per thread (`pipeline/extract_comments.py`).
- `MAX_SEEN_IDS = 200`: Deduplication window size.

## Automation

### Windows

- **Manual Run**: Double-click `run.bat` to update the feed immediately.
- **Scheduled Run**: Run `python scheduler.py` to keep the system updating every day at 11 PM local time. You can keep this running in a terminal or set it up as a Windows Task.

### Linux/VPS (Cron)

Set up a cron job:

```bash
0 23 * * * cd /path/to/tv-signal && python run_digest.py
```

## License

MIT
