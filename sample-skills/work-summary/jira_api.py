#!/usr/bin/env python3
"""Dependency-free Jira Cloud REST API helper."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


API_PATH = "/rest/api/3"
REQUEST_TIMEOUT_SECONDS = 30


class JiraHelperError(RuntimeError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def document_from_text(text: str) -> dict[str, Any]:
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": text}],
            }
        ],
    }


def environment() -> tuple[str, str, str]:
    missing = [
        name
        for name in ("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN")
        if not os.environ.get(name)
    ]
    if missing:
        raise JiraHelperError(
            "Missing required environment variable(s): " + ", ".join(missing)
        )

    base_url = os.environ["JIRA_BASE_URL"].rstrip("/")
    if not base_url.startswith("https://"):
        raise JiraHelperError("JIRA_BASE_URL must use https://")

    return base_url, os.environ["JIRA_EMAIL"], os.environ["JIRA_API_TOKEN"]


def error_message(response_body: bytes) -> str:
    try:
        payload = json.loads(response_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return response_body.decode("utf-8", errors="replace")[:500]

    messages: list[str] = []
    error_messages = payload.get("errorMessages", [])
    if isinstance(error_messages, list):
        messages.extend(str(message) for message in error_messages)

    errors = payload.get("errors", {})
    if isinstance(errors, dict):
        messages.extend(f"{key}: {value}" for key, value in errors.items())

    return "; ".join(messages) if messages else json.dumps(payload, ensure_ascii=False)


def request(
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    query: dict[str, Any] | None = None,
) -> Any:
    base_url, email, token = environment()
    url = base_url + API_PATH + path
    if query:
        url += "?" + urllib.parse.urlencode(query, doseq=True)

    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request_object = urllib.request.Request(url, data=body, method=method)
    credentials = base64.b64encode(f"{email}:{token}".encode("utf-8")).decode("ascii")
    request_object.add_header("Authorization", f"Basic {credentials}")
    request_object.add_header("Accept", "application/json")
    if body is not None:
        request_object.add_header("Content-Type", "application/json")

    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(request_object, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            response_body = response.read()
            if not response_body:
                return None
            return json.loads(response_body.decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise JiraHelperError(
            f"Jira API returned HTTP {error.code}: {error_message(error.read())}"
        ) from error
    except urllib.error.URLError as error:
        raise JiraHelperError(f"Could not reach Jira API: {error.reason}") from error
    except json.JSONDecodeError as error:
        raise JiraHelperError("Jira API returned invalid JSON") from error


def issue_path(issue_key: str) -> str:
    return "/issue/" + urllib.parse.quote(issue_key, safe="")


def parse_json_field(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError as error:
        raise JiraHelperError(f"Invalid JSON value: {value}") from error


def parse_field(value: str) -> tuple[str, str]:
    key, separator, field_value = value.partition("=")
    if not separator or not key:
        raise JiraHelperError(f"Invalid field assignment: {value}")
    return key, field_value


def command_search(args: argparse.Namespace) -> Any:
    payload: dict[str, Any] = {
        "jql": args.jql,
        "maxResults": args.max_results,
        "fields": args.fields,
    }
    if args.start_at:
        payload["startAt"] = args.start_at
    return request("POST", "/search", payload=payload)


def command_get(args: argparse.Namespace) -> Any:
    return request(
        "GET",
        issue_path(args.issue_key),
        query={"fields": ",".join(args.fields)},
    )


def command_comment(args: argparse.Namespace) -> Any:
    return request(
        "POST",
        issue_path(args.issue_key) + "/comment",
        payload={"body": document_from_text(args.body)},
    )


def command_transitions(args: argparse.Namespace) -> Any:
    return request("GET", issue_path(args.issue_key) + "/transitions")


def command_transition(args: argparse.Namespace) -> Any:
    payload: dict[str, Any] = {
        "transition": {"id": args.transition_id},
    }
    if args.comment:
        payload["update"] = {
            "comment": [{"add": {"body": document_from_text(args.comment)}}]
        }
    return request(
        "POST",
        issue_path(args.issue_key) + "/transitions",
        payload=payload,
    )


def command_update(args: argparse.Namespace) -> Any:
    fields: dict[str, Any] = {}
    if args.summary is not None:
        fields["summary"] = args.summary
    if args.description is not None:
        fields["description"] = document_from_text(args.description)
    fields.update(parse_field(value) for value in args.field)
    fields.update(
        {key: parse_json_field(value) for key, value in map(parse_field, args.json_field)}
    )

    if not fields:
        raise JiraHelperError("No update fields were provided")

    return request("PUT", issue_path(args.issue_key), payload={"fields": fields})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    search = subparsers.add_parser("search", help="Search issues with JQL")
    search.add_argument("--jql", required=True)
    search.add_argument("--max-results", type=int, default=50)
    search.add_argument("--start-at", type=int, default=0)
    search.add_argument(
        "--fields",
        nargs="+",
        default=["summary", "status", "priority", "updated"],
    )
    search.set_defaults(handler=command_search)

    get = subparsers.add_parser("get", help="Read one issue")
    get.add_argument("issue_key")
    get.add_argument(
        "--fields",
        nargs="+",
        default=["summary", "status", "priority", "updated", "assignee"],
    )
    get.set_defaults(handler=command_get)

    comment = subparsers.add_parser("comment", help="Add a comment")
    comment.add_argument("issue_key")
    comment.add_argument("--body", required=True)
    comment.set_defaults(handler=command_comment)

    transitions = subparsers.add_parser("transitions", help="List transitions")
    transitions.add_argument("issue_key")
    transitions.set_defaults(handler=command_transitions)

    transition = subparsers.add_parser("transition", help="Transition an issue")
    transition.add_argument("issue_key")
    transition.add_argument("--transition-id", required=True)
    transition.add_argument("--comment")
    transition.set_defaults(handler=command_transition)

    update = subparsers.add_parser("update", help="Update an issue")
    update.add_argument("issue_key")
    update.add_argument("--summary")
    update.add_argument("--description")
    update.add_argument("--field", action="append", default=[])
    update.add_argument("--json-field", action="append", default=[])
    update.set_defaults(handler=command_update)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        result = args.handler(args)
        if result is not None:
            json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
            sys.stdout.write("\n")
        return 0
    except JiraHelperError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("error: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
