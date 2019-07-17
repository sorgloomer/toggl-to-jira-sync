import datetime
import logging
from collections import namedtuple

import requests
from requests.auth import HTTPBasicAuth

from toggl_to_jira_sync import utils, dicts
from toggl_to_jira_sync.config import get_secrets
from toggl_to_jira_sync.core import WorklogEntry
from toggl_to_jira_sync.formats import datetime_toggl_format, datetime_jira_date_format, datetime_jira_format

logger = logging.getLogger(__name__)

JiraTag = namedtuple("JiraTag", ["id"])
TogglTag = namedtuple("TogglTag", ["id", "project_name", "project_pid", "billable", "jira_project"])


class TogglApi(object):
    def __init__(self, secrets=None):
        if secrets is None:
            secrets = get_secrets()
        self.secrets = secrets
        self.api_base = "https://www.toggl.com/api/"

    def _get(self, url, params=None):
        return self._request("get", url, params=params)

    def _request(self, method, url, params=None, json=None):
        resp = requests.request(
            method,
            self.api_base + url,
            auth=HTTPBasicAuth(self.secrets.toggl_apitoken, "api_token"),
            params=params,
            json=json
        )
        try:
            resp.raise_for_status()
        except:
            logger.debug(resp.text)
            raise
        return resp.json()

    def get_projects(self, workspace_id):
        return self._get("v8/workspaces/{workspace_id}/projects".format(workspace_id=workspace_id))

    def get_workspaces(self):
        return self._get("v8/workspaces")

    def get_entries(self, start_datetime=None, end_datetime=None):
        params = {}
        if start_datetime is not None:
            params["start_date"] = datetime_toggl_format.to_str(start_datetime)
        if end_datetime is not None:
            params["end_date"] = datetime_toggl_format.to_str(end_datetime)
        return self._get("v8/time_entries", params=params)

    def get_worklog(self, workspace_name, min_datetime=None, max_datetime=None):
        workspaces = self.get_workspaces()
        workspace = dicts.find_first(workspaces, name=workspace_name)
        projects = self.get_projects(workspace["id"])
        project_by_id = utils.index_by_id(projects)
        entries = self.get_entries(start_datetime=min_datetime, end_datetime=max_datetime)
        # TODO: check if this can return worklogs of other people, consider filtering for uid
        assert len(set(e["uid"] for e in entries)) <= 1
        worklog = [
            self._extract_entry(entry, project_by_id.get(entry.get("pid")), entry.get("pid"))
            for entry in entries
        ]
        return {
            "workspace": workspace,
            "projects": projects,
            "entries": entries,
            "worklog": worklog,
        }

    def update(self, id, data):
        self._put_entry(id, data)

    @classmethod
    def _extract_entry(cls, entry, project, project_pid):
        description = entry.get("description", "")
        issue = cls._extract_issue(description)
        jira_project = _extract_jira_project_from_issue(issue)
        start = datetime_toggl_format.from_str(entry.get("start"))
        stop = datetime_toggl_format.from_str(entry.get("stop"))
        return WorklogEntry(
            issue=issue,
            start=start,
            stop=stop,
            comment=description,
            tag=TogglTag(
                id=entry["id"],
                project_name=project["name"] if project is not None else None,
                project_pid=project_pid,
                billable=entry.get("billable"),
                jira_project=jira_project,
            ),
        )

    @staticmethod
    def _extract_issue(description):
        return utils.strip_after_any(description.strip(), (":", " ")).strip()

    def _get_entry(self, id):
        return self._get("v8/time_entries/{id}".format(id=id))

    def _put_entry(self, id, data):
        data = [
            ("description", data.get("comment")),
            ("start", data.get("start")),
            ("stop", data.get("stop")),
            ("pid", data.get("pid")),
            ("billable", data.get("billable")),
        ]
        data = {k: v for k, v in data if v is not None}
        return self._request("put", "v8/time_entries/{id}".format(id=id), json={"time_entry": data})


JiraWorklogFilter = namedtuple("JiraWorklogFilter", ["author", "min_date", "max_date"])


def _extract_jira_project_from_issue(issue):
    return utils.strip_after_any(issue, ["-"])


class JiraApi(object):
    def __init__(self, api_base, auth=None):
        self.api_base = api_base
        self.session = requests.Session()
        self.session.auth = auth

    def get_worklog(self, author=None, min_datetime=None, max_datetime=None):
        worklog_filter = JiraWorklogFilter(author=author, min_date=min_datetime, max_date=max_datetime)
        jql = self._assemble_jql(worklog_filter, date_error_margin=datetime.timedelta(days=1))
        worklog_resp = self.execute_jql(jql)
        worklog = self._get_filtered_worklogs(worklog_resp, worklog_filter)
        return {
            "jql": jql,
            "worklog_filter": worklog_filter,
            "worklog_resp": worklog_resp,
            "worklog": worklog,
        }

    def execute_jql(self, jql):
        return self._get("rest/api/2/search", params={"jql": jql})

    def _get_filtered_worklogs(self, resp, worklog_filter):
        return [
            worklog_item
            for issue in resp["issues"]
            for worklog_item in self._fetch_worklog(worklog_filter, issue)
        ]

    def delete_entry(self, issue, worklog_id):
        self._request(
            "delete",
            "rest/api/2/issue/{issue}/worklog/{worklog_id}".format(
                issue=issue,
                worklog_id=worklog_id,
            ))

    def add_entry(self, issue, data):
        start = datetime_jira_format.from_str(data["start"])
        stop = datetime_jira_format.from_str(data["stop"])
        duration = stop - start
        data = {
            "timeSpentSeconds": round(duration.total_seconds()),
            "started": data["start"],
            "comment": data["comment"],
        }
        logger.info(data)
        self._request("post", "rest/api/2/issue/{issue}/worklog".format(issue=issue), json=data)

    def _get(self, url, params=None):
        return self._request("get", url, params=params)

    def _request(self, method, url, params=None, json=None):
        resp = self.session.request(
            method,
            self.api_base + url,
            params=params,
            json=json,
        )
        try:
            resp.raise_for_status()
        except:
            logger.debug(resp.text)
            raise
        return resp.json()

    @staticmethod
    def _assemble_jql(worklog_filter, date_error_margin=None):
        if date_error_margin is None:
            date_error_margin = datetime.timedelta()
        filters = []
        if worklog_filter.author is not None:
            filters.append('worklogAuthor = "{value}"'.format(
                value=worklog_filter.author
            ))
        if worklog_filter.min_date is not None:
            filters.append('worklogDate >= "{value}"'.format(
                value=datetime_jira_date_format.to_str(worklog_filter.min_date - date_error_margin)
            ))
        if worklog_filter.max_date is not None:
            filters.append('worklogDate <= "{value}"'.format(
                value=datetime_jira_date_format.to_str(worklog_filter.max_date + date_error_margin)
            ))
        return " AND ".join(filters)

    def _fetch_worklog(self, worklog_filter, issue):
        resp = self._get("rest/api/2/issue/{key}/worklog".format(key=issue["key"]))
        for worklog in resp["worklogs"]:
            if self._worklog_matches_filter(worklog, worklog_filter):
                started = datetime_jira_format.from_str(worklog["started"])
                ended = started + datetime.timedelta(seconds=worklog["timeSpentSeconds"])
                yield WorklogEntry(
                    issue=issue["key"],
                    start=started,
                    stop=ended,
                    comment=worklog["comment"],
                    tag=JiraTag(id=worklog["id"]),
                )

    @staticmethod
    def _worklog_matches_filter(worklog_entry_dto, worklog_filter):
        if worklog_filter.author not in [worklog_entry_dto["author"]["key"], worklog_entry_dto["author"]["name"]]:
            return False
        started = datetime_jira_format.from_str(worklog_entry_dto["started"])
        if worklog_filter.min_date is not None and started < worklog_filter.min_date:
            return False
        if worklog_filter.max_date is not None and started > worklog_filter.max_date:
            return False
        return True