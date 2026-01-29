import time
import subprocess
import datetime
import logging
import os

# Configure logging for the scheduler
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] scheduler: %(message)s",
    handlers=[logging.FileHandler("logs/scheduler.log"), logging.StreamHandler()],
)


def run_job():
    logging.info("Starting scheduled run of run_digest.py")
    try:
        # Run the script and wait for it to finish
        result = subprocess.run(
            ["python", "run_digest.py"], check=True, capture_output=True, text=True
        )
        logging.info("Run successfully completed.")
        # Log last bit of output
        stdout_tail = (
            result.stdout[-500:] if len(result.stdout) > 500 else result.stdout
        )
        logging.info(f"Output tail:\n{stdout_tail}")
    except subprocess.CalledProcessError as e:
        logging.error(f"Run failed with exit code {e.returncode}")
        logging.error(f"Error output:\n{e.stderr}")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")


def get_seconds_until_target(hour, minute):
    """Calculates seconds until the next occurrence of hour:minute."""
    now = datetime.datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += datetime.timedelta(days=1)
    return (target - now).total_seconds()


def main():
    # Configuration
    TARGET_HOUR = 23  # 11 PM
    TARGET_MINUTE = 0

    logging.info("RSS Digest Scheduler started.")
    logging.info(
        f"Target run time: {TARGET_HOUR:02d}:{TARGET_MINUTE:02d} daily (local time)."
    )

    while True:
        seconds_wait = get_seconds_until_target(TARGET_HOUR, TARGET_MINUTE)
        next_run = datetime.datetime.now() + datetime.timedelta(seconds=seconds_wait)
        logging.info(
            f"Next run scheduled for: {next_run.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        logging.info(f"Waiting for {seconds_wait / 3600:.2f} hours...")

        # Sleep in increments so we can be interrupted if needed
        # (though in a simple script like this, time.sleep is fine)
        time.sleep(seconds_wait)

        run_job()
        # Small buffer to avoid double-triggering if time.sleep returns slightly early
        time.sleep(60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Scheduler stopped by user.")
    except Exception as e:
        logging.critical(f"Scheduler crashed: {e}")
