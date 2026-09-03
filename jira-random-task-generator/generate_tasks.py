#!/usr/bin/env python3
"""
generate_tasks.py - AI-alapú random Jira task generátor.

Egy megadott Jira projektbe (mindig Scrum módban) generál AI-val kitalált,
realisztikus task-okat:
  - user story-kat (önállóan), VAGY
  - N db epicet, mindegyiket a hozzá tartozó user story-kra bontva
    (prioritással, függőségekkel, start/due date-ekkel). Az epicek időablaka
    egymással átfedésben van, de nem ugyanakkor indulnak - valóságot
    szimulálva. Epicenként az első (függőség nélküli) story "In Progress"-be
    kerül az aktuális sprintben (opcionálisan hagyományos Story helyett Spike
    vagy POC típusként), a többi a backlogban marad.

A tool a projekt Scrum board/sprint állapotát is beállítja: ha nincs futó
sprint, létrehoz és elindít egyet.

A Vertex AI hívások automatikusan kezelik a globális és a regionális Gemini
modelleket is: elsőként a GOOGLE_CLOUD_LOCATION (default europe-west1)
location-nel próbálkozik, és ha a modell ott nem érhető el, automatikusan
átvált 'global'-ra (lásd README / GEMINI_LOCATION).

Használat:
    # Csak a Jira + Vertex AI kapcsolat ellenőrzése, tartalom generálása nélkül
    # - ezzel érdemes kezdeni
    uv run generate-jira-tasks --project DEMO --check-connection

    uv run generate-jira-tasks --project DEMO --count 2 --stories-per-epic 5 \
        --language hu --type epic --category dev
    uv run generate-jira-tasks --project DEMO --count 8 --language en --type story --dry-run
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta

from jira_lib.ai_client import AiClient, AiError
from jira_lib.config import Config, ConfigError
from jira_lib.jira_client import JiraClient, JiraError, bullet_list_adf, to_adf
from jira_lib.models import PlannedIssue
from jira_lib.planner import build_epic_plan, build_standalone_plan, stagger_epic_windows

EPIC_TYPE_CANDIDATES = ["Epic", "Epikus feladat", "Epika"]
STORY_TYPE_CANDIDATES = ["Story", "User Story", "Történet", "Felhasználói történet"]
SPIKE_TYPE_CANDIDATES = ["Spike", "Research Spike"]
POC_TYPE_CANDIDATES = ["POC", "Proof of Concept", "PoC", "Prototípus"]
START_DATE_FIELD_CANDIDATES = ["Start date", "Kezdés dátuma", "Kezdő dátum"]
IN_PROGRESS_TRANSITION_CANDIDATES = ["in progress", "folyamatban", "elkezdve"]

ACCEPTANCE_CRITERIA_LABELS = {"hu": "Elfogadási kritériumok:", "en": "Acceptance criteria:"}

# A klasszikus (company-managed) projekteknél a Jira Agile API a board type-ot
# 'scrum'-nak jelöli. A csapat-kezelt (team-managed / "next-gen") projekteknél
# viszont mindig 'simple' a type - attól függetlenül, hogy be van-e kapcsolva
# rajta a Sprints funkció -, ezért ezt is Scrum-kompatibilisnek kell tekinteni,
# és ténylegesen le kell kérdezni a sprinteket, hogy kiderüljön, működik-e.
SCRUM_COMPATIBLE_BOARD_TYPES = ("scrum", "simple")

FIRST_STORY_TYPE_CANDIDATES = {
    "spike": SPIKE_TYPE_CANDIDATES,
    "poc": POC_TYPE_CANDIDATES,
}

TYPICAL_EPIC_DURATION_DAYS = 12


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def warn(msg: str) -> None:
    print(f"[FIGYELEM] {msg}", file=sys.stderr)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI-alapú random Jira task generátor (Scrum)")
    parser.add_argument(
        "--project", "-p", required=True,
        help="Jira projekt (Space) kulcs, pl. DEMO - a Space URL-jében látható project key",
    )
    parser.add_argument(
        "--count", "-c", type=int, default=5,
        help="type=story esetén hány önálló story; type=epic esetén hány epic készüljön (default: 5)",
    )
    parser.add_argument(
        "--stories-per-epic", "-s", type=int, default=4,
        help="Epicenként hány user story készüljön (csak type=epic esetén, default: 4)",
    )
    parser.add_argument("--language", "-l", choices=["hu", "en"], default="hu", help="Generált tartalom nyelve")
    parser.add_argument("--type", "-t", choices=["epic", "story"], default="story", help="Task típus: epic (bontással) vagy önálló story")
    parser.add_argument(
        "--category", "-k", choices=["dev", "test", "devops"], default="dev",
        help="Feladat kategória: fejlesztési, tesztelési vagy devops jellegű tartalom (default: dev)",
    )
    parser.add_argument(
        "--first-story-type", "-f", choices=["story", "spike", "poc"], default="story",
        help="Epicenként az első (In Progress-be kerülő) elem típusa: hagyományos story, Spike vagy POC (default: story)",
    )
    parser.add_argument("--topic", "-o", default=None, help="Opcionális témajavaslat az AI-nak (pl. 'fizetési modul'); ha nincs megadva, kategóriánként véletlenszerű")
    parser.add_argument("--epic-issue-type", "-E", default=None, help="Epic issue type neve felülírásra, ha nem 'Epic'")
    parser.add_argument("--story-issue-type", "-S", default=None, help="Story issue type neve felülírásra, ha nem 'Story'")
    parser.add_argument("--dry-run", "-d", action="store_true", help="Csak a tervet írja ki, Jira-ba nem ír")
    parser.add_argument(
        "--check-connection", "-x", action="store_true",
        help="Csak a Jira és a Vertex AI kapcsolatot teszteli (nem generál, nem ír semmit), majd kilép",
    )
    return parser.parse_args(argv)


def ensure_scrum_board_and_sprint(jira: JiraClient, project_key: str) -> tuple[dict | None, dict | None]:
    """A projekt mindig Scrum módban dolgozik: megkeresi a projekt Scrum-kompatibilis
    boardját (klasszikus Scrum vagy csapat-kezelt 'simple' típusú, Sprints funkcióval),
    és ha nincs futó sprint, létrehoz és elindít egyet."""
    boards = jira.get_boards_for_project(project_key)
    matching = [b for b in boards if b.get("type") in SCRUM_COMPATIBLE_BOARD_TYPES]

    if not matching:
        available = ", ".join(sorted({b.get("type", "?") for b in boards})) or "nincs board"
        warn(
            f"Nem található Scrum-kompatibilis board a(z) {project_key} projekthez "
            f"(elérhető típusok: {available}). Hozz létre egy Scrum boardot a projekthez, "
            "vagy csapat-kezelt (team-managed) projekt esetén kapcsold be a Sprints "
            "funkciót (Project settings → Features → Sprints). Addig a sprint-kezelést "
            "kihagyom, és a task-ok sima backlog issue-ként jönnek létre."
        )
        return None, None

    board = matching[0]
    try:
        active = jira.get_sprints_for_board(board["id"], state="active")
    except JiraError as exc:
        warn(
            f"A(z) '{board.get('name')}' boardon nem érhető el a Sprints funkció ({exc}). "
            "Csapat-kezelt (team-managed) projekt esetén kapcsold be: Project settings → "
            "Features → Sprints. Addig a sprint-kezelést kihagyom, és a task-ok sima "
            "backlog issue-ként jönnek létre."
        )
        return board, None
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


def resolve_first_story_type_id(
    jira: JiraClient, project_key: str, flag: str, fallback_type_id: str, fallback_label: str
) -> tuple[str, str]:
    """Az epicenkénti 'első' elem issue type ID-ja a --first-story-type kapcsoló alapján
    (spike/poc), hiba-toleráns visszaeséssel a sima story típusra, ha az instance-en
    nincs ilyen issue type konfigurálva a projektben."""
    if flag == "story":
        return fallback_type_id, fallback_label

    candidates = FIRST_STORY_TYPE_CANDIDATES[flag]
    try:
        type_id = jira.find_issue_type_id(project_key, candidates)
        return type_id, flag.upper()
    except JiraError as exc:
        warn(
            f"Nem található '{flag.upper()}' jellegű issue type a projektben ({exc}). "
            "Az epicek első eleme helyette sima Story típussal jön létre."
        )
        return fallback_type_id, fallback_label


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


def print_plan(planned: list[PlannedIssue], epic_title: str | None, window: tuple[date, date] | None = None) -> None:
    if epic_title:
        window_str = f" [{window[0].isoformat()} -> {window[1].isoformat()}]" if window else ""
        print(f"\nEPIC: {epic_title}{window_str}")
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


def create_planned_issues(
    jira: JiraClient,
    project_key: str,
    planned: list[PlannedIssue],
    story_type_id: str,
    first_story_type_id: str,
    epic_key: str,
    category: str,
    start_date_field_id: str | None,
    language: str,
) -> None:
    ac_label = ACCEPTANCE_CRITERIA_LABELS.get(language, ACCEPTANCE_CRITERIA_LABELS["en"])
    for issue in planned:
        desc = to_adf(issue.description)
        if issue.acceptance_criteria:
            desc["content"].append(
                {"type": "paragraph", "content": [{"type": "text", "text": ac_label}]}
            )
            desc["content"].append(bullet_list_adf(issue.acceptance_criteria))

        optional_fields = {
            "priority": {"name": issue.priority_name},
            "duedate": issue.due_date,
            "parent": {"key": epic_key},
            "labels": [category],
        }
        if start_date_field_id and issue.start_date:
            optional_fields[start_date_field_id] = issue.start_date

        type_id = first_story_type_id if issue.is_first else story_type_id
        issue.jira_key = create_issue_with_optional_fields(
            jira,
            {
                "project": {"key": project_key},
                "issuetype": {"id": type_id},
                "summary": issue.title,
                "description": desc,
            },
            optional_fields,
        )
        log(f"Story létrehozva: {issue.jira_key} - {issue.title}")


def link_dependencies(jira: JiraClient, planned: list[PlannedIssue]) -> None:
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


def start_first_story(jira: JiraClient, planned: list[PlannedIssue], sprint: dict | None) -> None:
    first = next((p for p in planned if p.is_first), None)
    if not first or not first.jira_key:
        return

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


def check_connection(args: argparse.Namespace) -> int:
    """Kapcsolati teszt: kizárólag azt ellenőrzi, hogy a Jira és a Vertex AI
    integráció elérhető és helyesen konfigurált-e. Nem generál tartalmat, és
    semmit nem hoz létre vagy módosít Jira-ban."""
    try:
        config = Config.load()
    except ConfigError as exc:
        log(f"Konfigurációs hiba: {exc}")
        return 2

    ok = True

    print("== Jira kapcsolat ==")
    jira: JiraClient | None
    try:
        jira = JiraClient(config.jira_base_url, config.jira_email, config.jira_api_token)
        me = jira.get_current_user()
        who = me.get("displayName") or me.get("emailAddress") or "?"
        print(f"  [OK] Hitelesítve mint: {who} ({config.jira_base_url})")
    except JiraError as exc:
        ok = False
        jira = None
        print(f"  [HIBA] Jira hitelesítés sikertelen: {exc}")

    if jira is not None:
        try:
            project = jira.get_project(args.project)
            print(f"  [OK] Projekt elérhető: {project['key']} - {project.get('name', '')}")
        except JiraError as exc:
            ok = False
            print(f"  [HIBA] Projekt '{args.project}' nem érhető el: {exc}")

        try:
            boards = jira.get_boards_for_project(args.project)
            scrum_boards = [b for b in boards if b.get("type") in SCRUM_COMPATIBLE_BOARD_TYPES]
            if not scrum_boards:
                found = ", ".join(sorted({b.get("type", "?") for b in boards})) or "nincs board"
                print(f"  [FIGYELEM] Nincs Scrum-kompatibilis board a projekthez (elérhető típus(ok): {found})")
            else:
                board = scrum_boards[0]
                kind = " (csapat-kezelt/'simple' board)" if board.get("type") == "simple" else ""
                try:
                    jira.get_sprints_for_board(board["id"], state="active")
                    print(f"  [OK] Scrum-kompatibilis board, Sprints elérhető: {board.get('name')}{kind}")
                except JiraError as exc:
                    print(
                        f"  [FIGYELEM] Board megvan ({board.get('name')}{kind}), de a Sprints funkció "
                        f"nem érhető el rajta ({exc}). Csapat-kezelt projekt esetén kapcsold be: "
                        "Project settings → Features → Sprints."
                    )
        except JiraError as exc:
            ok = False
            print(f"  [HIBA] Board lekérdezés sikertelen: {exc}")

    print("\n== Vertex AI (Gemini) kapcsolat ==")
    primary_location, fallback_location = config.ai_locations()
    location_desc = primary_location if not fallback_location else f"{primary_location} (fallback: {fallback_location})"
    print(f"  Konfiguráció: project='{config.gcp_project}', location={location_desc}, modell='{config.gemini_model}'")
    ai = AiClient(config.gcp_project, primary_location, fallback_location, config.gemini_model)
    success, message = ai.test_connection()
    print(f"  [{'OK' if success else 'HIBA'}] {message}")
    ok = ok and success

    print("\n" + ("Minden ellenőrzés sikeres." if ok else "Volt sikertelen ellenőrzés, lásd fent."))
    return 0 if ok else 1


def run(args: argparse.Namespace) -> int:
    if args.check_connection:
        return check_connection(args)

    try:
        config = Config.load()
    except ConfigError as exc:
        log(f"Konfigurációs hiba: {exc}")
        return 2

    jira = JiraClient(config.jira_base_url, config.jira_email, config.jira_api_token)
    ai = AiClient(config.gcp_project, *config.ai_locations(), config.gemini_model)

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

    sprint = None
    if not args.dry_run:
        _board, sprint = ensure_scrum_board_and_sprint(jira, args.project)
    else:
        log("[dry-run] Scrum board/sprint beállítás kihagyva")

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

        first_story_type_id, first_story_label = story_type_id, "Story"
        if not args.dry_run:
            first_story_type_id, first_story_label = resolve_first_story_type_id(
                jira, args.project, args.first_story_type, story_type_id, "Story"
            )

        base_start = date.fromisoformat(sprint["startDate"][:10]) if sprint and sprint.get("startDate") else date.today()
        windows = stagger_epic_windows(args.count, base_start, TYPICAL_EPIC_DURATION_DAYS)

        created_epics: list[tuple[str, list[str]]] = []

        for epic_index in range(args.count):
            window_start, window_end = windows[epic_index]
            log(
                f"AI generálás ({epic_index + 1}/{args.count}. epic): epic + "
                f"{args.stories_per_epic} story ({args.language}, kategória={args.category}, "
                f"első elem={first_story_label})..."
            )
            epic_plan = ai.generate_epic_with_stories(
                args.language, args.stories_per_epic, priority_names, args.topic, args.category
            )
            planned = build_epic_plan(epic_plan.stories, priority_names, window_start, window_end)

            if args.dry_run:
                print_plan(planned, epic_plan.epic_title, (window_start, window_end))
                continue

            epic_key = create_issue_with_optional_fields(
                jira,
                {
                    "project": {"key": args.project},
                    "issuetype": {"id": epic_type_id},
                    "summary": epic_plan.epic_title,
                    "description": to_adf(epic_plan.epic_description),
                },
                {"labels": [args.category]},
            )
            log(f"Epic létrehozva: {epic_key} ({window_start.isoformat()} -> {window_end.isoformat()})")

            create_planned_issues(
                jira, args.project, planned, story_type_id, first_story_type_id,
                epic_key, args.category, start_date_field_id, args.language,
            )
            link_dependencies(jira, planned)
            start_first_story(jira, planned, sprint)

            created_epics.append((epic_key, [p.jira_key for p in planned]))

        if args.dry_run:
            return 0

        for epic_key, story_keys in created_epics:
            print(f"\nKész. Epic: {epic_key}, story-k: {story_keys}")
        return 0

    # -- önálló story-k (nincs epic bontás) --------------------------------------
    log(f"AI generálás: {args.count} önálló story ({args.language}, kategória={args.category})...")
    task_list = ai.generate_standalone_tasks(args.language, args.count, priority_names, args.category)
    planned = build_standalone_plan(task_list.tasks, priority_names)

    if args.dry_run:
        print_plan(planned, epic_title=None)
        return 0

    ac_label = ACCEPTANCE_CRITERIA_LABELS.get(args.language, ACCEPTANCE_CRITERIA_LABELS["en"])
    for issue in planned:
        desc = to_adf(issue.description)
        if issue.acceptance_criteria:
            desc["content"].append(
                {"type": "paragraph", "content": [{"type": "text", "text": ac_label}]}
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
            {"priority": {"name": issue.priority_name}, "labels": [args.category]},
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
    except AiError as exc:
        log(f"Vertex AI hiba: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
