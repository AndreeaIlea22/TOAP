import json
import time

from doajtest.helpers import DoajTestCase, apply_test_case_config
from portality import constants
from portality.bll import background_task_status
from portality.bll.background_task_status import is_stable
from portality.lib import dates
from portality.models import BackgroundJob
from portality.tasks.anon_export import AnonExportBackgroundTask
from portality.tasks.journal_csv import JournalCSVBackgroundTask


def save_mock_bgjob(action=None, status=None, created_before_sec=0, is_save=True,
                    queue_type=None):
    bgjob = BackgroundJob()

    if action:
        bgjob.action = JournalCSVBackgroundTask.__action__

    if status:
        bgjob._set_with_struct("status", status)

    if created_before_sec != 0:
        bgjob.set_created(dates.format(dates.before_now(created_before_sec)))

    if queue_type:
        bgjob.queue_type = queue_type

    if is_save:
        bgjob.save()

    return bgjob


# config BG_MONITOR_ERRORS_CONFIG
bg_monitor_errors_config__empty = {
    'BG_MONITOR_ERRORS_CONFIG': {}
}

bg_monitor_errors_config__a = {
    'BG_MONITOR_ERRORS_CONFIG': {
        JournalCSVBackgroundTask.__action__: {
            'check_sec': 3600,
            'allowed_num_err': 0,
        }
    }
}

bg_monitor_errors_config__b = {
    'BG_MONITOR_ERRORS_CONFIG': {
        'kajdlaksj': {
            'check_sec': 3600,
            'allowed_num_err': 0,
        }
    }
}

# config BG_MONITOR_QUEUED_CONFIG
bg_monitor_queued_config__a = {
    'BG_MONITOR_QUEUED_CONFIG': {
        'journal_csv': {
            'total': 99999999,
            'oldest': 1200,
        }
    }
}

bg_monitor_queued_config__zero_total = {
    'BG_MONITOR_QUEUED_CONFIG': {
        'journal_csv': {
            'total': 0,
            'oldest': 1200,
        }
    }
}

# config BG_MONITOR_LAST_COMPLETED
bg_monitor_last_completed__now = {
    'BG_MONITOR_LAST_COMPLETED': {
        'main_queue': 0,
        'long_running': 0,
    }
}

bg_monitor_last_completed__a = {
    'BG_MONITOR_LAST_COMPLETED': {
        'main_queue': 10000,
        'long_running': 10000,
    }
}


class TestBackgroundTaskStatus(DoajTestCase):

    @staticmethod
    def assert_stable_dict(val: dict):
        assert is_stable(val.get('status'))
        assert len(val.get('err_msgs')) == 0

    @staticmethod
    def assert_unstable_dict(val):
        assert not is_stable(val.get('status'))
        assert len(val.get('err_msgs'))

    @apply_test_case_config(bg_monitor_last_completed__now)
    def test_create_background_status__invalid_last_completed__main_queue(self):
        save_mock_bgjob(JournalCSVBackgroundTask.__action__,
                        queue_type=constants.BGJOB_QUEUE_TYPE_MAIN,
                        status=constants.BGJOB_STATUS_COMPLETE, )

        time.sleep(2)

        status_dict = background_task_status.create_background_status()

        assert not is_stable(status_dict['status'])
        self.assert_unstable_dict(status_dict['queues'].get('main_queue', {}))
        self.assert_stable_dict(status_dict['queues'].get('long_running', {}))

    @apply_test_case_config(bg_monitor_last_completed__now)
    def test_create_background_status__invalid_last_completed__long_running(self):
        save_mock_bgjob(AnonExportBackgroundTask.__action__,
                        queue_type=constants.BGJOB_QUEUE_TYPE_LONG,
                        status=constants.BGJOB_STATUS_COMPLETE, )

        time.sleep(2)

        status_dict = background_task_status.create_background_status()

        assert not is_stable(status_dict['status'])
        self.assert_stable_dict(status_dict['queues'].get('main_queue', {}))
        self.assert_unstable_dict(status_dict['queues'].get('long_running', {}))

    @apply_test_case_config(bg_monitor_last_completed__a)
    def test_create_background_status__valid_last_completed(self):
        save_mock_bgjob(JournalCSVBackgroundTask.__action__,
                        queue_type=constants.BGJOB_QUEUE_TYPE_MAIN,
                        status=constants.BGJOB_STATUS_COMPLETE, )
        save_mock_bgjob(AnonExportBackgroundTask.__action__,
                        queue_type=constants.BGJOB_QUEUE_TYPE_LONG,
                        status=constants.BGJOB_STATUS_COMPLETE, )

        time.sleep(2)

        status_dict = background_task_status.create_background_status()

        assert is_stable(status_dict['status'])
        self.assert_stable_dict(status_dict['queues'].get('main_queue', {}))
        self.assert_stable_dict(status_dict['queues'].get('long_running', {}))

    @apply_test_case_config(bg_monitor_last_completed__now)
    def test_create_background_status__valid_last_completed__no_record(self):
        status_dict = background_task_status.create_background_status()
        assert is_stable(status_dict['status'])

    @apply_test_case_config(bg_monitor_errors_config__empty)
    def test_create_background_status__empty_errors_config(self):
        save_mock_bgjob(JournalCSVBackgroundTask.__action__,
                        status=constants.BGJOB_STATUS_ERROR, )

        time.sleep(2)

        status_dict = background_task_status.create_background_status()

        journal_csv_dict = status_dict['queues']['main_queue']['errors'].get(JournalCSVBackgroundTask.__action__, {})

        assert is_stable(status_dict['status'])
        assert not journal_csv_dict

    @apply_test_case_config(bg_monitor_errors_config__a)
    def test_create_background_status__error_in_period_found(self):
        save_mock_bgjob(JournalCSVBackgroundTask.__action__,
                        status=constants.BGJOB_STATUS_ERROR, )

        time.sleep(2)

        status_dict = background_task_status.create_background_status()

        journal_csv_dict = status_dict['queues']['main_queue']['errors'].get(JournalCSVBackgroundTask.__action__, {})

        assert not is_stable(status_dict['status'])
        self.assert_unstable_dict(journal_csv_dict)
        assert journal_csv_dict.get('in_monitoring_period', 0) > 0

    @apply_test_case_config(bg_monitor_errors_config__a)
    def test_create_background_status__error_in_period_not_found(self):
        save_mock_bgjob(JournalCSVBackgroundTask.__action__,
                        status=constants.BGJOB_STATUS_ERROR,
                        created_before_sec=1000000000)

        time.sleep(2)

        status_dict = background_task_status.create_background_status()

        journal_csv_dict = status_dict['queues']['main_queue']['errors'].get(JournalCSVBackgroundTask.__action__, {})

        assert is_stable(status_dict['status'])
        self.assert_stable_dict(journal_csv_dict)
        assert journal_csv_dict.get('in_monitoring_period', 0) == 0

    @apply_test_case_config(bg_monitor_queued_config__zero_total)
    def test_create_background_status__queued_invalid_total(self):
        save_mock_bgjob(JournalCSVBackgroundTask.__action__,
                        status=constants.BGJOB_STATUS_QUEUED, )

        time.sleep(2)
        status_dict = background_task_status.create_background_status()

        journal_csv_dict = status_dict['queues']['main_queue']['queued'].get(JournalCSVBackgroundTask.__action__, {})

        assert not is_stable(status_dict['status'])
        assert journal_csv_dict.get('total', 0)
        self.assert_unstable_dict(journal_csv_dict)

    @apply_test_case_config(bg_monitor_queued_config__zero_total)
    def test_create_background_status__queued_valid_total(self):
        save_mock_bgjob(JournalCSVBackgroundTask.__action__,
                        status=constants.BGJOB_STATUS_COMPLETE, )

        time.sleep(2)
        status_dict = background_task_status.create_background_status()

        journal_csv_dict = status_dict['queues']['main_queue']['queued'].get(JournalCSVBackgroundTask.__action__, {})

        assert is_stable(status_dict['status'])
        assert journal_csv_dict.get('total', 0) == 0
        self.assert_stable_dict(journal_csv_dict)

    @apply_test_case_config(bg_monitor_queued_config__a)
    def test_create_background_status__queued_invalid_oldest(self):
        save_mock_bgjob(JournalCSVBackgroundTask.__action__,
                        status=constants.BGJOB_STATUS_QUEUED,
                        created_before_sec=1000000000)

        time.sleep(2)
        status_dict = background_task_status.create_background_status()

        journal_csv_dict = status_dict['queues']['main_queue']['queued'].get(JournalCSVBackgroundTask.__action__, {})

        assert not is_stable(status_dict['status'])
        self.assert_unstable_dict(journal_csv_dict)
        assert journal_csv_dict.get('oldest') is not None

    @apply_test_case_config(bg_monitor_queued_config__a)
    def test_create_background_status__queued_valid_oldest(self):
        save_mock_bgjob(JournalCSVBackgroundTask.__action__,
                        status=constants.BGJOB_STATUS_QUEUED, )

        time.sleep(2)
        status_dict = background_task_status.create_background_status()
        print(json.dumps(status_dict, indent=4))

        journal_csv_dict = status_dict['queues']['main_queue']['queued'].get(JournalCSVBackgroundTask.__action__, {})

        assert is_stable(status_dict['status'])
        self.assert_stable_dict(journal_csv_dict)
        assert journal_csv_dict.get('oldest') is not None
