"""Worker process: takes jobs from the queue and runs the agents.

Run one or more:  python -m app.worker
"""
import logging
import os
import signal
import socket
import threading
import time

from . import heartbeat, jobqueue, jobs, runs, sandbox

log = logging.getLogger("runbookpilot.worker")

IDLE_SLEEP_SECONDS = 1.0
STALE_CHECK_SECONDS = 60
HEARTBEAT_SECONDS = 30
SCHEDULE_CHECK_SECONDS = 30


class Worker:
    def __init__(self) -> None:
        self.id = f"{socket.gethostname()}-{os.getpid()}"
        self.stopping = False

    def stop(self, *_):
        log.info("Stopping after the current job")
        self.stopping = True

    def run_forever(self) -> None:
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)
        log.info("Worker %s waiting for jobs", self.id)
        # Heartbeats run on their own thread so the worker stays "online" during long jobs.
        threading.Thread(target=self._heartbeat_loop, daemon=True).start()
        last_stale_check = last_schedule_check = 0.0
        while not self.stopping:
            if time.monotonic() - last_schedule_check > SCHEDULE_CHECK_SECONDS:
                try:
                    if started := runs.run_due_schedules():
                        log.info("Started %d scheduled run(s)", started)
                except Exception:
                    log.exception("Scheduler check failed")
                last_schedule_check = time.monotonic()
            if time.monotonic() - last_stale_check > STALE_CHECK_SECONDS:
                if requeued := jobqueue.requeue_stale():
                    log.warning("Requeued %d stale job(s)", requeued)
                last_stale_check = time.monotonic()
            if not self.run_one():
                time.sleep(IDLE_SLEEP_SECONDS)
        heartbeat.remove(self.id)

    def _heartbeat_loop(self) -> None:
        while not self.stopping:
            try:
                self.beat()
            except Exception:
                log.exception("Heartbeat failed")
            time.sleep(HEARTBEAT_SECONDS)

    def beat(self) -> None:
        state = sandbox.status()
        heartbeat.beat(self.id, state.get("ready", False), state.get("detail") or f"Docker {state.get('engine', '')}".strip())

    def run_one(self) -> bool:
        """Run the next job if there is one. Returns False when the queue is empty."""
        job = jobqueue.claim(self.id)
        if job is None:
            return False
        log.info("Job %s: %s for runbook %s", job["id"], job["kind"], job["runbook_id"])
        error = jobs.run(job["kind"], job["runbook_id"], job["payload"])
        jobqueue.finish(job["id"], error)
        return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    Worker().run_forever()
