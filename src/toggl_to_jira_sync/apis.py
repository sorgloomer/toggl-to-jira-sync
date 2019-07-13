import datetime
import pprint
from collections import namedtuple

import requests
from requests.auth import HTTPBasicAuth

from toggl_to_jira_sync import utils, dicts
from toggl_to_jira_sync.config import get_secrets
from toggl_to_jira_sync.core import WorklogEntry
from toggl_to_jira_sync.formats import datetime_toggl_format, datetime_jira_date_format, datetime_jira_format

JiraTag = namedtuple("JiraTag", ["id"])
TogglTag = namedtuple("TogglTag", ["id", "project", "billable"])


class TogglApi(object):
    def __init__(self, secrets=None):
        if secrets is None:
            secrets = get_secrets()
        self.secrets = secrets
        self.api_base = "https://www.toggl.com/api/"

    def _get(self, url, params=None):
        resp = requests.get(
            self.api_base + url,
            auth=HTTPBasicAuth(self.secrets.toggl_apitoken, "api_token"),
            params=params,
        )
        resp.raise_for_status()
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

    @utils.transform_result(list)
    def get_worklog(self, workspace_name, min_datetime=None, max_datetime=None):
        workspaces = self.get_workspaces()
        workspace = dicts.find_first(workspaces, name=workspace_name)
        projects = self.get_projects(workspace["id"])
        project_by_id = utils.index_by_id(projects)
        entries = self.get_entries(start_datetime=min_datetime, end_datetime=max_datetime)
        assert len(set(e["uid"] for e in entries)) <= 1
        pprint.pprint(entries)
        for entry in entries:
            project = project_by_id.get(entry.get("pid"))
            yield self._extract_entry(entry, project)

    @classmethod
    def _extract_entry(cls, entry, project):
        description = entry["description"]
        return WorklogEntry(
            issue=cls._extract_issue(description),
            start=datetime_toggl_format.from_str(entry["start"]),
            stop=datetime_toggl_format.from_str(entry["stop"]),
            comment=description,
            tag=TogglTag(
                id=entry["id"],
                project=project["name"] if project is not None else None,
                billable=entry["billable"],
            ),
        )

    @staticmethod
    def _extract_issue(description):
        return utils.strip_after_any(description.strip(), (":", " ")).strip()


JiraWorklogFilter = namedtuple("JiraWorklogFilter", ["author", "min_date", "max_date"])


class JiraApi(object):
    def __init__(self, api_base, auth=None):
        self.api_base = api_base
        self.session = requests.Session()
        self.session.auth = auth

    def get_worklog(self, author=None, min_datetime=None, max_datetime=None):
        worklog_filter = JiraWorklogFilter(author=author, min_date=min_datetime, max_date=max_datetime)
        jql = self._assemble_jql(worklog_filter, date_error_margin=datetime.timedelta(days=1))
        resp = self.execute_jql(jql)
        return self._get_filtered_worklogs(resp, worklog_filter)

    def execute_jql(self, jql):
        return self._get("rest/api/2/search", params={"jql": jql})

    def _get_filtered_worklogs(self, resp, worklog_filter):
        return [
            worklog_item
            for issue in resp["issues"]
            for worklog_item in self._fetch_worklog(worklog_filter, issue)
        ]

    def _get(self, url, params=None):
        resp = self.session.get(
            self.api_base + url,
            params=params,
        )
        resp.raise_for_status()
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
