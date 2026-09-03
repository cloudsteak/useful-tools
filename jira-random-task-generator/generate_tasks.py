#!/usr/bin/env python3
"""
generate_tasks.py - AI-alapú random Jira task generátor.

Egy megadott Jira projektbe generál AI-val kitalált, realisztikus task-okat:
  - user story-kat (önállóan), VAGY
  - egy epicet, ami N user story-ra van bontva (prioritással, függőségekkel,
    start/due date-ekkel; az első story "In Progress"-ben az aktuális
    sprintben indul, a többi a backlogban marad).

A tool a projekt board/sprint állapotát is beállítja: ha "scrum" módot kérsz
és nincs futó sprint, létrehoz és elindít egyet.

Használat:
    uv run generate-jira-tasks --project DEMO --count 5 --language hu --type epic
    uv run generate-jira-tasks --project DEMO --count 8 --language en --type story --dry-run
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta

from jira_lib.ai_client import AiClient
from jira_lib.config import Config, ConfigError
from jira_lib.jira_client import JiraClient, JiraError, bullet_list_adf, to_adf
from jira_lib.models import PlannedIssue
from jira_lib.planner import build_epic_plan, build_standalone_plan

EPIC_TYPE_CANDIDATES = ["Epic", "Epikus feladat", "Epika"]
STORY_TYPE_CANDIDATES = ["Story", "User Story", "Történet", "Felhasználói történet"]
START_DATE_FIELD_CANDIDATES = ["Start date", "Kezdés dátuma", "Kezdő dátum"]
IN_PROGRESS_TRANSITION_CANDIDATES = ["in progress", "folyamatban", "elkezdve"]


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def warn(msg: str) -> None:
    print(f"[FIGYELEM] {msg}", file=sys.stderr)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI-alapú random Jira task generátor")
    parser.add_argument("--project", "-p", required=True, help="Jira projekt kulcs, pl. DEMO")
    parser.add_argument("--count", "-c", type=int, default=5, help="Hány story/epic-alatti story készüljön (default: 5)")
    parser.add_argument("--language", "-l", choices=["hu", "en"], default="hu", help="Generált tartalom nyelve")
    parser.add_argument("--type", "-t", choices=["epic", "story"], default="story", help="Task típus: epic (bontással) vagy önálló story")
    parser.add_argument("--board-type", choices=["kanban", "scrum"], default=None, help="Board/sprint kezelés módja (default: epic->scrum, story->kanban)")
    parser.add_argument("--topic", default=None, help="Opcionális témajavaslat az AI-nak (pl. 'fizetési modul')")
    parser.add_argument("--epic-issue-type", default=None, help="Epic issue type neve felülírásra, ha nem 'Epic'")
    parser.add_argument("--story-issue-type", default=None, help="Story issue type neve felülírásra, ha nem 'Story'")
    parser.add_argument("--dry-run", action="store_true", help="Csak a tervet írja ki, Jira-ba nem ír")
    return parser.parse_args(argv)


def ensure_board_and_sprint(
    jira: JiraClient, project_key: str, board_type: str
) -> tuple[dict | None, dict | None]:
    boards = jira.get_boards_for_project(project_key)
    matching = [b for b in boards if b.get("type") == board_type]

    if not matching:
        available = ", ".join(sorted({b.get("type", "?") for b in boards})) or "nincs board"
        warn(
            f"Nem található '{board_type}' típusú board a(z) {project_key} projekthez "
            f"(elérhető típusok: {available}). A Jira Cloud API nem támogatja meglévő "
            "projekt board-típusának API-n keresztüli átváltását, ezért a sprint-kezelést "
            "kihagyom, és a task-ok sima backlog issue-ként jönnek létre."
        )
        return None, None

    board = matching[0]
    if board_type != "scrum":
        return board, None

    active = jira.get_sprints_for_board(board["id"], state="active")
    if active:
        return board, active[0]

    future = jira.get_sprints_for_board(board["id"], state="future")
    today = date.today()
    end = today + timedelta(days=14)

    if future:
        sprint = future[0]
        try:
            sprint = jira.start_sprint(sprint["id"], today.isoformat(), end.isoformat())
            log(f"Meglévő tervezett sprint elindítva: {sprint.get('name')}")
            return board, sprint
        except JiraError as exc:
            warn(f"Nem sikerült elindítani a meglévő sprintet: {exc}")
            return board, None

    try:
        sprint = jira.create_sprint(
            board["id"], f"Sprint {today.isoformat()}", today.isoformat(), end.isoformat()
        )
        sprint = jira.start_sprint(sprint["id"], today.isoformat(), end.isoformat())
        log(f"Új sprint létrehozva és elindítva: {sprint.get('name')}")
        return board, sprint
    except JiraError as exc:
        warn(f"Nem sikerült sprintet létrehozni/indítani: {exc}")
        return board, None


def resolve_priority_names(jira: JiraClient) -> list[str]:
    priorities = jira.get_priorities()
    names = [p["name"] for p in priorities]
    if not names:
        raise JiraError("A Jira instance-en nincs egyetlen priority sem beállítva.")
    return names


def create_issue_with_optional_fields(
    jira: JiraClient,
    required_fields: dict,
    optional_fields: dict,
) -> str:
    """Issue létrehozása minimál mezőkkel, majd az opcionális mezők egyenkénti,
    hiba-toleráns beállítása (screen-konfigurációtól függően nem minden instance-en
    elérhető minden mező, ezért ez nem szabad hogy megállítsa a futást)."""
    created = jira.create_issue(required_fields)
    key = created["key"]

    for field_name, field_value in optional_fields.items():
        try:
            jira.update_issue(key, {field_name: field_value})
        except JiraError as exc:
            warn(f"{key}: '{field_name}' mező beállítása sikertelen ({exc}). Kihagyva.")

    return key


def find_transition_id(jira: JiraClient, issue_key: str, name_candidates: list[str]) -> str | None:
    transitions = jira.get_transitions(issue_key)
    lowered_candidates = [c.lower() for c in name_candidates]
    for transition in transitions:
        name = transition.get("name", "").strip().lower()
        if any(cand in name for cand in lowered_candidates):
            return transition["id"]
    return None


def print_plan(planned: list[PlannedIssue], epic_title: str | None) -> None:
    if epic_title:
        print(f"\nEPIC: {epic_title}")
        print("-" * 60)
    for issue in planned:
        marker = " [FIRST -> In Progress + sprint]" if issue.is_first else ""
        deps = f" | depends_on={issue.depends_on}" if issue.depends_on else ""
        dates = ""
        if issue.start_date or issue.due_date:
            dates = f" | {issue.start_date} -> {issue.due_date}"
        print(
            f"  [{issue.index}] {issue.title} | priority={issue.priority_name} "
            f"| points={issue.story_points}{dates}{deps}{marker}"
        )
        for ac in issue.acceptance_criteria:
            print(f"        - {ac}")


def run(args: argparse.Namespace) -> int:
    try:
        config = Config.load()
    except ConfigError as exc:
        log(f"Konfigurációs hiba: {exc}")
        return 2

    jira = JiraClient(config.jira_base_url, config.jira_email, config.jira_api_token)
    ai = AiClient(config.gcp_project, config.gcp_location, config.gemini_model)

    try:
        project = jira.get_project(args.project)
    except JiraError as exc:
        log(f"A(z) '{args.project}' projekt nem érhető el: {exc}")
        return 1
    log(f"Projekt: {project['key']} - {project.get('name', '')}")

    try:
        priority_names = resolve_priority_names(jira)
        story_type_id = jira.find_issue_type_id(
            args.project, [args.story_issue_type] if args.story_issue_type else STORY_TYPE_CANDIDATES
        )
    except JiraError as exc:
        log(f"Metaadat lekérdezés sikertelen: {exc}")
        return 1

    board_type = args.board_type or ("scrum" if args.type == "epic" else "kanban")
    sprint = None
    if not args.dry_run:
        _board, sprint = ensure_board_and_sprint(jira, args.project, board_type)
    else:
        log(f"[dry-run] board-type='{board_type}' beállítás kihagyva")

    start_date_field_id = None
    if args.type == "epic" and not args.dry_run:
        start_date_field_id = jira.find_field_id(START_DATE_FIELD_CANDIDATES)
        if start_date_field_id is None:
            warn(
                "Nem található 'Start date' mező ezen az instance-en, "
                "a start dátumokat nem tudom beállítani (csak a due date-et)."
            )

    if args.type == "epic":
        try:
            epic_type_id = jira.find_issue_type_id(
                args.project, [args.epic_issue_type] if args.epic_issue_type else EPIC_TYPE_CANDIDATES
            )
        except JiraError as exc:
            log(f"Epic issue type nem található: {exc}")
            return 1

        log(f"AI generálás: epic + {args.count} story ({args.language})...")
        epic_plan = ai.generate_epic_with_stories(args.language, args.count, priority_names, args.topic)
        planned = build_epic_plan(
            epic_plan.stories,
            priority_names,
            date.fromisoformat(sprint["startDate"][:10]) if sprint and sprint.get("startDate") else None,
            date.fromisoformat(sprint["endDate"][:10]) if sprint and sprint.get("endDate") else None,
        )

        if args.dry_run:
            print_plan(planned, epic_plan.epic_title)
            return 0

        epic_key = create_issue_with_optional_fields(
            jira,
            {
                "project": {"key": args.project},
                "issuetype": {"id": epic_type_id},
                "summary": epic_plan.epic_title,
                "description": to_adf(epic_plan.epic_description),
            },
            {},
        )
        log(f"Epic létrehozva: {epic_key}")

        for issue in planned:
            desc = to_adf(issue.description)
            if issue.acceptance_criteria:
                desc["content"].append(
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": "Elfogadási kritériumok:"}],
                    }
                )
                desc["content"].append(bullet_list_adf(issue.acceptance_criteria))

            optional_fields = {
                "priority": {"name": issue.priority_name},
                "duedate": issue.due_date,
                "parent": {"key": epic_key},
            }
            if start_date_field_id and issue.start_date:
                optional_fields[start_date_field_id] = issue.start_date

            issue.jira_key = create_issue_with_optional_fields(
                jira,
                {
                    "project": {"key": args.project},
                    "issuetype": {"id": story_type_id},
                    "summary": issue.title,
                    "description": desc,
                },
                optional_fields,
            )
            log(f"Story létrehozva: {issue.jira_key} - {issue.title}")

        by_index = {p.index: p for p in planned}
        for issue in planned:
            for dep_idx in issue.depends_on:
                dep_issue = by_index.get(dep_idx)
                if not dep_issue or not dep_issue.jira_key or not issue.jira_key:
                    continue
                try:
                    jira.create_issue_link("Blocks", inward_key=issue.jira_key, outward_key=dep_issue.jira_key)
                except JiraError as exc:
                    warn(f"Link létrehozása sikertelen ({dep_issue.jira_key} blocks {issue.jira_key}): {exc}")

        first = next((p for p in planned if p.is_first), None)
        if first and first.jira_key:
            if sprint:
                try:
                    jira.add_issues_to_sprint(sprint["id"], [first.jira_key])
                    log(f"{first.jira_key} hozzáadva a sprinthez: {sprint.get('name')}")
                except JiraError as exc:
                    warn(f"Sprinthez adás sikertelen ({first.jira_key}): {exc}")
            transition_id = find_transition_id(jira, first.jira_key, IN_PROGRESS_TRANSITION_CANDIDATES)
            if transition_id:
                try:
                    jira.transition_issue(first.jira_key, transition_id)
                    log(f"{first.jira_key} -> In Progress")
                except JiraError as exc:
                    warn(f"Státusz váltás sikertelen ({first.jira_key}): {exc}")
            else:
                warn(f"{first.jira_key}: nem található 'In Progress' jellegű transition.")

        print(f"\nKész. Epic: {epic_key}, story-k: {[p.jira_key for p in planned]}")
        return 0

    # -- önálló story-k (nincs epic bontás) --------------------------------------
    log(f"AI generálás: {args.count} önálló story ({args.language})...")
    task_list = ai.generate_standalone_tasks(args.language, args.count, priority_names)
    planned = build_standalone_plan(task_list.tasks, priority_names)

    if args.dry_run:
        print_plan(planned, epic_title=None)
        return 0

    for issue in planned:
        desc = to_adf(issue.description)
        if issue.acceptance_criteria:
            desc["content"].append(
                {"type": "paragraph", "content": [{"type": "text", "text": "Elfogadási kritériumok:"}]}
            )
            desc["content"].append(bullet_list_adf(issue.acceptance_criteria))

        issue.jira_key = create_issue_with_optional_fields(
            jira,
            {
                "project": {"key": args.project},
                "issuetype": {"id": story_type_id},
                "summary": issue.title,
                "description": desc,
            },
            {"priority": {"name": issue.priority_name}},
        )
        log(f"Story létrehozva: {issue.jira_key} - {issue.title}")

    print(f"\nKész. Létrehozott story-k: {[p.jira_key for p in planned]}")
    return 0


def main() -> None:
    args = parse_args()
    try:
        sys.exit(run(args))
    except JiraError as exc:
        log(f"Jira hiba: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
