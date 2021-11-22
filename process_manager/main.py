from __init__ import ProcessManager
import datetime
import logging

from bin import SchedulerTask
from scheduler import Scheduler

def set_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s: %(message)s")
    handler.setFormatter(fmt)
    logger.addHandler(handler)

if __name__ == "__main__":
    
    # TODO: This is going to be moved to a config file
    config = {
        'biannual_bins': {
            'amount': 1,
            'bin_size': 2,
            'n_threads': 2,
            'length': datetime.timedelta(seconds=30),
            'float_after': datetime.timedelta(seconds=10),
            'start': datetime.datetime(2020, 1, 1, 0, 0, 0)
        },
        'weekly_bins': {
            'amount': 1,
            'bin_size': 2,
            'n_threads': 2,
            'length': datetime.timedelta(seconds=30),
            'float_after': datetime.timedelta(seconds=10),
            'start': datetime.datetime(2020, 1, 1, 0, 0, 0)
        },
        'custom_bins': {
            'amount': 1,
            'bin_size': 2,
            'n_threads': 2,
            'length': datetime.timedelta(seconds=30),
            'float_after': datetime.timedelta(seconds=10),
            'start': datetime.datetime(2020, 1, 1, 0, 0, 0)
        },
        'realtime_bins': {
            'amount': 1,
            'length': datetime.timedelta(seconds=30),
            'float_after': datetime.timedelta(seconds=10),
            'start': datetime.datetime(2020, 1, 1, 0, 0, 0)
        }
        
    }

    set_logging()
    manager = ProcessManager(config)
    scheduler = Scheduler()
    task = SchedulerTask(datetime.datetime(2020, 1, 1, 0, 0, 0), datetime.datetime(2020, 1, 1, 1, 0, 0), 2, False, scheduler)
    manager.add_task(task)
    manager.run()
