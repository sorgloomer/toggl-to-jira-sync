import logging
from collections import namedtuple

from toggl_to_jira_sync import utils
from toggl_to_jira_sync.formats import datetime_toggl_format, datetime_jira_format

logger = logging.getLogger(__name__)


class MessageLevel:
    info = "info"
    warning = "warning"
    danger = "danger"


Message = namedtuple("Message", ["message", "level"])
JIRA_FIELDS = {"started", "timeSpentSeconds", "comment"}


class ActionRecorder(object):
    def __init__(self, issue, toggl_id, jira_id):
        self.messages = []
        self._toggl_updates = dict()
        self._jira_updates = dict()
        self._jira_delete = False
        self._jira_create = False
        self._toggl_id = toggl_id
        self._jira_id = jira_id
        self._issue = issue

    def message(self, message, level, context=None):
        if context is None:
            context = {}
        self.messages.append(Message(
            message=message.format(**context),
            level=level
        ))

    def toggl_update(self, **kwargs):
        self._toggl_updates.update(kwargs)

    def jira_update(self, key, value):
        assert key in JIRA_FIELDS
        self._jira_updates[key] = value

    def jira_create(self, data):
        assert set(data) == JIRA_FIELDS
        self._jira_create = True
        self._jira_updates.update(data)

    def jira_delete(self):
        self._jira_delete = True

    def serialize(self):
        result = []
        if self._toggl_updates:
            result.append({
                "type": "toggl",
                "action": "update",
                "id": self._toggl_id,
                "values": self._toggl_updates,
                "issue": self._issue,
            })
        if self._jira_delete:
            result.append({
                "type": "jira",
                "action": "delete",
                "id": self._jira_id,
                "issue": self._issue,
            })
        if self._jira_create:
            result.append({
                "type": "jira",
                "action": "create",
                "values": self._jira_updates,
                "issue": self._issue,
            })
        elif not self._jira_delete and self._jira_updates:
            result.append({
                "type": "jira",
                "action": "update",
                "id": self._jira_id,
                "values": self._jira_updates,
                "issue": self._issue,
            })
        return result


class DiffGather(object):
    def __init__(self, settings, projects):
        toggl_projects_by_name = utils.index_by(projects, "name")
        self.toggl_projects_by_key = {
            k: toggl_projects_by_name[v.toggl_project] if v.toggl_project is not None else None
            for k, v in settings.projects.items()
        }
        self.settings = settings

    def gather_diff(self, pairing):
        toggl = pairing["toggl"]
        jira = pairing["jira"]

        recorder = ActionRecorder(
            issue=toggl.issue if toggl is not None else jira.issue,
            toggl_id=toggl.tag.id if toggl is not None else None,
            jira_id=jira.tag.id if jira is not None else None,
        )

        _gather_diff(
            recorder=recorder,
            toggl=toggl,
            jira=jira,
            diff_params=self,
        )

        return {
            "actions": recorder.serialize(),
            "messages": recorder.messages,
        }


def _gather_diff(recorder, toggl, jira, diff_params):
    if toggl is None:
        if jira is not None:
            recorder.message("Remove Jira entry", MessageLevel.danger)
            recorder.jira_delete()
        return

    project_setting = diff_params.settings.projects.get(toggl.tag.jira_project)
    if project_setting is None:
        recorder.message("Project {!r} is not set up".format(toggl.tag.jira_project), MessageLevel.warning)
        return

    expected_billable = project_setting.toggl_billable
    if toggl.tag.billable != expected_billable:
        recorder.message("Update Toggl billability to {}".format(expected_billable), MessageLevel.info)
        recorder.toggl_update(billable=expected_billable)

    expected_pid = _get_expected_project_pid(toggl, diff_params)
    if expected_pid is not None and toggl.tag.project_pid != expected_pid:
        recorder.message("Update Toggl project", MessageLevel.warning)
        recorder.toggl_update(pid=expected_pid)

    toggl_comment = toggl.comment
    toggl_start_new = _floor_minute(toggl.start)
    if toggl.start != toggl_start_new:
        recorder.message("Align Toggl start", MessageLevel.info)
        recorder.toggl_update(start=datetime_toggl_format.to_str(toggl_start_new))

    toggl_stop_new = _floor_minute(toggl.stop)
    if toggl.stop != toggl_stop_new:
        recorder.message("Align Toggl stop", MessageLevel.info)
        recorder.toggl_update(stop=datetime_toggl_format.to_str(toggl_stop_new))

    if project_setting.jira_skip:
        if jira is None:
            recorder.message("Skip for Jira", MessageLevel.info)
        else:
            recorder.message("Delete Jira entry", MessageLevel.danger)
            recorder.jira_delete()
        return

    duration_seconds = round((toggl_stop_new - toggl_start_new).total_seconds())
    expected_jira = {
        "started": datetime_jira_format.to_str(toggl_start_new),
        "timeSpentSeconds": duration_seconds,
        "comment": toggl_comment,
    }

    if jira is None:
        recorder.message("Create jira entry", MessageLevel.danger)
        recorder.jira_create(expected_jira)
        return

    if jira.issue != toggl.issue:
        recorder.message("Move Jira worklog to other task", MessageLevel.danger)
        recorder.jira_delete()
        recorder.jira_create(expected_jira)
        return

    def _jira_field(fieldname, message, level, equality=None):
        if equality is None:
            equality = _identity

        actual = jira.tag.raw_entry[fieldname]
        expected = expected_jira[fieldname]
        if equality(actual) != equality(expected):
            logger.info("Jira field %s differs, actual: %s expected: %s", fieldname, actual, expected)
            recorder.message(message, level)
            recorder.jira_update(fieldname, expected)

    _jira_field("started", "Sync Jira started", MessageLevel.danger, equality=datetime_jira_format.from_str)
    _jira_field("timeSpentSeconds", "Sync Jira timeSpentSeconds", MessageLevel.danger)
    _jira_field("comment", "Sync Jira comment", MessageLevel.warning)


def _identity(x):
    return x


def _get_expected_project_pid(toggl, diff_params):
    project = diff_params.toggl_projects_by_key.get(toggl.tag.jira_project)
    return project["id"] if project is not None else None


def _floor_minute(dt):
    if dt is None:
        return None
    return dt.replace(second=0, microsecond=0)
