import os

from apscheduler.schedulers.blocking import BlockingScheduler

from .services.jobs import sync_source


def main():
    interval = max(1, int(os.getenv("SYNC_INTERVAL_MINUTES", "5")))
    scheduler = BlockingScheduler()
    scheduler.add_job(sync_source, "interval", minutes=interval, id="source-sync", max_instances=1, coalesce=True, misfire_grace_time=60)
    scheduler.start()


if __name__ == "__main__":
    main()