"""Belső adatmodellek: AI kimenet és a végrehajtási terv (plan)."""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# AI structured-output sémák (Gemini response_schema-hoz)
# ---------------------------------------------------------------------------


class StoryContent(BaseModel):
    title: str = Field(description="Rövid, egyértelmű user story cím")
    description: str = Field(
        description=(
            "A user story leírása KÖTELEZŐEN a szabvány "
            "'As a <szerepkör>, I want <cél>, so that <haszon>' sablon szerint, "
            "a kért nyelvre lefordítva (pl. magyarul: "
            "'Mint <szerepkör>, szeretném <cél>, azért hogy <haszon>'). "
            "Ne térj el ettől a szerkezettől, és ne keverd a két nyelvet."
        )
    )
    acceptance_criteria: list[str] = Field(
        description="3-6 konkrét, ellenőrizhető elfogadási kritérium", default_factory=list
    )
    story_points: int = Field(description="Becsült story point (Fibonacci: 1,2,3,5,8,13)")
    priority_rank: int = Field(
        description="Prioritás rangsor: 1 = legmagasabb prioritás, nagyobb szám = alacsonyabb"
    )
    depends_on: list[int] = Field(
        description=(
            "Azon másik story-k 0-indexelt sorszáma, amiktől EZ a story függ "
            "(azok előbb kell elkészüljenek). Üres lista, ha nincs függőség."
        ),
        default_factory=list,
    )


class EpicPlan(BaseModel):
    epic_title: str = Field(description="Rövid epic cím")
    epic_description: str = Field(description="Az epic üzleti célja és hatóköre")
    stories: list[StoryContent] = Field(description="Az epicet lefedő user story-k listája")


class StandaloneTask(BaseModel):
    title: str = Field(description="Rövid, egyértelmű task/user story cím")
    description: str = Field(
        description=(
            "A user story leírása KÖTELEZŐEN a szabvány "
            "'As a <szerepkör>, I want <cél>, so that <haszon>' sablon szerint, "
            "a kért nyelvre lefordítva (pl. magyarul: "
            "'Mint <szerepkör>, szeretném <cél>, azért hogy <haszon>'). "
            "Ne térj el ettől a szerkezettől, és ne keverd a két nyelvet."
        )
    )
    acceptance_criteria: list[str] = Field(default_factory=list)
    story_points: int = Field(description="Becsült story point (Fibonacci: 1,2,3,5,8,13)")
    priority_rank: int = Field(
        description="Prioritás rangsor: 1 = legmagasabb prioritás, nagyobb szám = alacsonyabb"
    )


class StandaloneTaskList(BaseModel):
    tasks: list[StandaloneTask]


# ---------------------------------------------------------------------------
# Végrehajtási terv (a planner tölti fel, a Jira létrehozó ezt fogyasztja)
# ---------------------------------------------------------------------------


@dataclass
class PlannedIssue:
    index: int
    title: str
    description: str
    acceptance_criteria: list[str]
    story_points: int
    priority_name: str
    depends_on: list[int] = field(default_factory=list)
    start_date: str | None = None  # ISO yyyy-mm-dd
    due_date: str | None = None  # ISO yyyy-mm-dd
    is_first: bool = False

    # kitöltve létrehozás után
    jira_key: str | None = None
