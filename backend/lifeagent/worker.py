"""Worker infrastructure entry point. No Agent task execution is implemented yet."""
import argparse
import logging
import signal
import threading
from lifeagent.database import readiness


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    ready, reason = readiness()
    if not ready:
        raise SystemExit('Database not ready: ' + reason)
    if args.check:
        print('Worker database dependencies are ready; execution queue is not implemented.')
        return
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    logging.info('Worker standby. DEV-02 has no execution queue; no tasks will be consumed.')
    stopped = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stopped.set())
    while not stopped.wait(30):
        if not readiness()[0]:
            raise SystemExit('Database became unavailable')


if __name__ == '__main__':
    main()
