from . import settingsloader, service, actions
from .core import calculate_pairing


def inspect_interval(min_datetime, max_datetime):
    settings = settingsloader.get_settings()
    apis = service.get_apis(settings=settings)
    if apis.secrets is None:
        raise RuntimeError("Secrets not set up")
    jira_worklog = apis.jira.get_worklog(
        author=apis.secrets.jira_username,
        min_datetime=min_datetime,
        max_datetime=max_datetime,
    )
    toggl_worklog = apis.toggl.get_worklog(
        workspace_name=settings.toggl_workspace_name,
        min_datetime=min_datetime,
        max_datetime=max_datetime,
    )
    pairings = calculate_pairing(toggl_worklog["worklog"], jira_worklog["worklog"])
    diff_gatherer = actions.DiffGather(settings=settings, projects=toggl_worklog["projects"])
    rows = [
        determine_actions_and_map(pairing, diff_gatherer)
        for pairing in pairings
    ]
    return dict(
        rows=rows,
        projects=toggl_worklog["projects"],
        entries=toggl_worklog["entries"],
    )


def determine_actions_and_map(pairing, diff_gatherer):
    diff = diff_gatherer.gather_diff(pairing)
    return {
        "toggl": pairing["toggl"],
        "jira": pairing["jira"],
        "dist": pairing["dist"],
        "start": pairing["start"],
        "actions": diff["actions"],
        "messages": diff["messages"],
    }
