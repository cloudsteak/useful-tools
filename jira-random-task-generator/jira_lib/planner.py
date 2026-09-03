"""Üzleti logika: prioritás feloldás, függőség-gráf tisztítás, dátum-elosztás."""

from __future__ import annotations

import random
from datetime import date, timedelta

from .models import PlannedIssue, StandaloneTask, StoryContent


def _priority_name(rank: int, priority_names: list[str]) -> str:
    """1-indexelt rank (1 = legmagasabb) -> tényleges Jira priority név, clampelve."""
    if not priority_names:
        raise ValueError("A Jira instance-en nincs egyetlen priority sem.")
    idx = max(1, min(rank, len(priority_names))) - 1
    return priority_names[idx]


def _clean_dependencies(stories: list[StoryContent]) -> list[list[int]]:
    """depends_on listák tisztítása: önhivatkozás, tartományon kívüli index és
    kör (ciklus) kiszűrése DFS-sel. Ciklus esetén az utolsó, kört záró élet dobjuk el."""
    n = len(stories)
    deps: list[list[int]] = []
    for i, story in enumerate(stories):
        cleaned = sorted({d for d in story.depends_on if 0 <= d < n and d != i})
        deps.append(cleaned)

    WHITE, GRAY, BLACK = 0, 1, 2
    color = [WHITE] * n

    def dfs(node: int, stack: list[int]) -> None:
        color[node] = GRAY
        stack.append(node)
        for dep in list(deps[node]):
            if color[dep] == GRAY:
                # kör detektálva: az élt (node -> dep) eldobjuk, hogy megszakadjon
                deps[node].remove(dep)
                continue
            if color[dep] == WHITE:
                dfs(dep, stack)
        stack.pop()
        color[node] = BLACK

    for i in range(n):
        if color[i] == WHITE:
            dfs(i, [])

    return deps


def _topological_order(n: int, deps: list[list[int]]) -> list[int]:
    visited = [False] * n
    order: list[int] = []

    def visit(node: int) -> None:
        if visited[node]:
            return
        visited[node] = True
        for dep in deps[node]:
            visit(dep)
        order.append(node)

    for i in range(n):
        visit(i)
    return order  # dependency mindig a saját indexe előtt szerepel


def build_epic_plan(
    stories: list[StoryContent],
    priority_names: list[str],
    epic_window_start: date | None,
    epic_window_end: date | None,
) -> list[PlannedIssue]:
    """Epic alá tartozó story-k teljes terve: prioritás, tisztított függőség,
    topológiai sorrend alapján dátumok, és az 'első' (In Progress-be kerülő) story.

    Az epic_window_start/epic_window_end az adott epic saját (más epicekkel
    átfedésben lévő) időablaka, lásd stagger_epic_windows()."""
    n = len(stories)
    deps = _clean_dependencies(stories)
    order = _topological_order(n, deps)

    if epic_window_start is not None and epic_window_end is not None and epic_window_end > epic_window_start:
        window_start, window_end = epic_window_start, epic_window_end
    else:
        window_start = date.today()
        window_end = window_start + timedelta(days=max(7, n * 2))

    total_days = max(1, (window_end - window_start).days)
    step = max(1, total_days // max(1, n))

    planned: list[PlannedIssue] = [None] * n  # type: ignore[list-item]
    for position, idx in enumerate(order):
        story = stories[idx]
        start_offset = min(position * step, total_days - 1)
        story_start = window_start + timedelta(days=start_offset)
        duration_days = max(1, (story.story_points + 1) // 2)
        story_due = min(story_start + timedelta(days=duration_days), window_end)
        if story_due <= story_start:
            story_due = story_start + timedelta(days=1)

        planned[idx] = PlannedIssue(
            index=idx,
            title=story.title,
            description=story.description,
            acceptance_criteria=story.acceptance_criteria,
            story_points=story.story_points,
            priority_name=_priority_name(story.priority_rank, priority_names),
            depends_on=deps[idx],
            start_date=story_start.isoformat(),
            due_date=story_due.isoformat(),
        )

    # az "első" story: a topológiai sorrendben legelső, aminek nincs függősége
    first_idx = next((idx for idx in order if not deps[idx]), order[0])
    planned[first_idx].is_first = True

    return planned


def stagger_epic_windows(
    epic_count: int,
    base_start: date,
    typical_duration_days: int = 10,
) -> list[tuple[date, date]]:
    """Több epic egymást átfedő, de el nem csúszásmentes (nem egyszerre induló)
    időablakát adja vissza, valóságot szimulálva: minden következő epic
    valamennyi (véletlenszerű, de sosem 0) nappal később indul, mint az előző,
    és a saját maga is véletlenszerűen változó hosszúságú - így az epicek
    munkája jellemzően időben átfedésbe kerül egymással, anélkül hogy
    ugyanazon a napon indulnának."""
    windows: list[tuple[date, date]] = []
    cursor = base_start
    min_stagger = max(1, typical_duration_days // 5)
    max_stagger = max(min_stagger + 1, typical_duration_days // 2)
    for i in range(epic_count):
        start = cursor
        duration = random.randint(
            max(3, typical_duration_days - 3), typical_duration_days + 5
        )
        end = start + timedelta(days=duration)
        windows.append((start, end))
        cursor = start + timedelta(days=random.randint(min_stagger, max_stagger))
    return windows


def build_standalone_plan(tasks: list[StandaloneTask], priority_names: list[str]) -> list[PlannedIssue]:
    planned: list[PlannedIssue] = []
    for i, task in enumerate(tasks):
        planned.append(
            PlannedIssue(
                index=i,
                title=task.title,
                description=task.description,
                acceptance_criteria=task.acceptance_criteria,
                story_points=task.story_points,
                priority_name=_priority_name(task.priority_rank, priority_names),
            )
        )
    return planned
