---
name: work-summary
description: Summarize open GitHub PRs, open GitHub issues, and assigned Jira items into a Markdown work summary.
---

# Work Summary

Use this skill when the user wants a current summary of their open work across GitHub and Jira.

## Inputs

- GitHub login: use `@me` unless the user specifies another login.
- Jira user: use `currentUser()` unless the user specifies another user.
- Time window: default to all open work; use a date filter only if the user asks for one.

## Required environment

- GitHub: authenticated `gh`
- Jira: `JIRA_BASE_URL`, `JIRA_EMAIL`, and `JIRA_API_TOKEN`

If Jira credentials are missing, still produce the GitHub summary and note that Jira was unavailable.

## Data to collect

### GitHub

Use `gh search` so the query is not limited to the current repository.

```bash
gh search prs \
  --assignee "@me" \
  --state open \
  --limit 100 \
  --json number,title,url,repository,updatedAt,isDraft,reviewDecision

gh search issues \
  --assignee "@me" \
  --state open \
  --limit 100 \
  --json number,title,url,repository,updatedAt,labels
```

### Jira

Use the Python helper bundled with this skill:

```bash
python3 <skill-directory>/jira_api.py search \
  --jql 'assignee = currentUser() AND statusCategory != Done ORDER BY status ASC, updated DESC' \
  --max-results 100
```

## Report format

Write the report to:

```text
/sandbox/output/work-summary.md
```

Use this structure:

```markdown
# Work Summary

## GitHub pull requests
| PR | Repository | Status | Updated | Notes |
|---|---|---|---|---|

## GitHub issues
| Issue | Repository | Labels | Updated |
|---|---|---|---|

## Jira items
| Issue | Summary | Status | Priority | Updated |
|---|---|---|---|---|

## To do
- Items that are clearly not started or are blocked

## In progress
- Items that are actively being worked on

## Needs attention
- Items that are stale, blocked, or waiting on review
```

Do not invent statuses, priorities, or dates. If a field is missing, write `unknown`.

## Output handoff

After writing the report, tell the user:

```bash
openshell sandbox download <sandbox-name> /sandbox/output/work-summary.md .
```
