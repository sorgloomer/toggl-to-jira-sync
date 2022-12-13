Toggl to Jira sync
==================

This app allows you to sync your Toggl logs into Jira.

You just create a new Toggl entry, and provide a description like
`EXAMPLE-123 created pullrequest for this issue`. This connector will
automatically:

 - set the entry to billable
 - set a project for the entry
 - will create a corresponding Jira worklog entry with the same
   description

if set up correctly (won't work for today if your timer is currently running)


How to use
----------

 - [Python 3.x](https://www.python.org/downloads/)
 - configure the application
   - create a `settings.json` based on `settings.example.json` to
     tell the application how Toggl projects should be mapped to Jira
   - create a `secrets.json` based on `secrets.example.json` and provide
     your Toggl and Jira credentials 
     (In case of Jira you should use the Jira associated email address and an api token as password)
 - setup and activate virtualenv
   `source install.sh`
   or
   `call install.bat`
   the scripts will install and setup virtualenv
 - call `run-once`

The `settings.example.json` file contains oddly specific examples: the Jira projects the AODocs DMS team is working with.
If you are in this team, you can ust copy this file to your `settings.json` and you're good to go.