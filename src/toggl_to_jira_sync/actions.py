from collections import OrderedDict, namedtuple

from toggl_to_jira_sync import utils
from toggl_to_jira_sync.formats import datetime_toggl_format, datetime_jira_format


class MessageLevel:
    info = "info"
    warning = "warning"
    danger = "danger"


Message = namedtuple("Message", ["message", "level"])


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
            message= message.format(**context),
            level=level
        ))

    def toggl_update(self, **kwargs):
        self._toggl_updates.update(kwargs)

    def jira_update(self, **kwargs):
        self._jira_updates.update(kwargs)

    def jira_create(self, start, stop, comment):
        self._jira_create = True
        self._jira_updates.update(
            start=start,
            stop=stop,
            comment=comment,
        )

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
    def __init__(self, secrets, projects):
        projects_by_name = utils.index_by(projects, "name")
        self.projects_by_key = {
            k: projects_by_name[v]
            for k, v in secrets.toggl_projects.items()
        }
        self.secrets = secrets

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
            recorder.message("Remove jira entry", MessageLevel.danger)
            recorder.jira_delete()
        return

    expected_billable = toggl.tag.jira_project not in diff_params.secrets.toggl_nonbillable
    if toggl.tag.billable != expected_billable:
        recorder.message("Update toggl billability to {}".format(expected_billable), MessageLevel.info)
        recorder.toggl_update(billable=expected_billable)

    expected_pid = _get_expected_project_pid(toggl, diff_params)
    if expected_pid is not None and toggl.tag.project_pid != expected_pid:
        recorder.message("Update toggl project", MessageLevel.warning)
        recorder.toggl_update(pid=expected_pid)

    toggl_comment = toggl.comment
    toggl_start_new = _floor_minue(toggl.start)
    if toggl.start != toggl_start_new:
        recorder.message("Align toggl start", MessageLevel.info)
        recorder.toggl_update(start=datetime_toggl_format.to_str(toggl_start_new))

    toggl_stop_new = _floor_minue(toggl.stop)
    if toggl.stop != toggl_stop_new:
        recorder.message("Align toggl stop", MessageLevel.info)
        recorder.toggl_update(stop=datetime_toggl_format.to_str(toggl_stop_new))

    if toggl.tag.jira_project in diff_params.secrets.jira_projects_skip:
        if jira is None:
            recorder.message("Skip for jira", MessageLevel.info)
        else:
            recorder.message("Delete jira entry", MessageLevel.danger)
            recorder.jira_delete()
        return

    expected_jira = dict(
        start=datetime_jira_format.to_str(toggl_start_new),
        stop=datetime_jira_format.to_str(toggl_stop_new),
        comment=toggl_comment
    )

    if jira is None:
        recorder.message("Create jira entry", MessageLevel.danger)
        recorder.jira_create(**expected_jira)
        return

    if jira.issue != toggl.issue:
        recorder.message("Move Jira worklog to other task", MessageLevel.danger)
        recorder.jira_delete()
        recorder.jira_create(**expected_jira)
        return

    if jira.start != toggl_start_new:
        recorder.message("Sync jira start", MessageLevel.danger)
        recorder.jira_update(start=expected_jira["start"])

    if jira.stop != toggl_stop_new:
        recorder.message("Sync jira stop", MessageLevel.danger)
        recorder.jira_update(stop=expected_jira["stop"])

    if jira.comment != toggl_comment:
        recorder.message("Sync jira comment", MessageLevel.warning)
        recorder.jira_update(comment=expected_jira["comment"])


def _get_expected_project_pid(toggl, diff_params):
    project = diff_params.projects_by_key.get(toggl.tag.jira_project.lower())
    return project["id"] if project is not None else None


def _floor_minue(dt):
    if dt is None:
        return None
    return dt.replace(second=0, microsecond=0)
