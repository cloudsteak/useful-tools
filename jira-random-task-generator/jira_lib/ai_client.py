"""Vertex AI (Gemini) kliens strukturált task-tartalom generálásához."""

from __future__ import annotations

import random

from google import genai
from google.genai import types

from .models import EpicPlan, StandaloneTaskList

_LANGUAGE_NAMES = {"hu": "magyar", "en": "English"}

_CATEGORY_LABELS = {
    "dev": "fejlesztési (szoftverfejlesztési)",
    "test": "tesztelési (minőségbiztosítási / QA)",
    "devops": "DevOps / infrastruktúra",
}

_CATEGORY_TOPICS: dict[str, list[str]] = {
    "dev": [
        "e-commerce checkout folyamat fejlesztése",
        "belső admin dashboard",
        "mobil app push notification rendszer",
        "ügyfélszolgálati ticketing integráció",
        "fizetési szolgáltató integráció",
        "felhasználói onboarding élmény",
        "riportolási / analitikai modul",
        "keresés és szűrés funkció",
        "jogosultságkezelés és SSO",
        "teljesítmény-optimalizálás és caching",
        "API rate limiting és monitoring",
        "többnyelvű (i18n) támogatás",
    ],
    "test": [
        "end-to-end teszt automatizálás bevezetése",
        "regressziós teszt csomag bővítése",
        "teljesítmény- és terheléses tesztelés",
        "teszt adat generátor építése",
        "API kontrakt tesztek bevezetése",
        "exploratory testing session szervezése",
        "biztonsági (penetrációs) teszt előkészítés",
        "accessibility (a11y) audit és javítás",
        "teszt lefedettség növelése kritikus modulokon",
        "vizuális regressziós tesztelés bevezetése",
        "mobil app kompatibilitási tesztmátrix kialakítása",
        "CI-ba integrált smoke teszt csomag",
    ],
    "devops": [
        "CI/CD pipeline fejlesztés és gyorsítás",
        "Kubernetes cluster upgrade és hardening",
        "infrastruktúra mint kód (Terraform) refaktor",
        "monitoring és alerting bevezetése (Prometheus/Grafana)",
        "log aggregáció bevezetése (ELK/Loki)",
        "secrets kezelés bevezetése (Vault)",
        "autoscaling és kapacitástervezés",
        "disaster recovery terv kidolgozása és tesztelése",
        "container image build pipeline optimalizálás",
        "blue-green / canary deployment bevezetése",
        "költségoptimalizálás a felhő infrastruktúrán",
        "zero-downtime adatbázis migráció automatizálása",
    ],
}


def _pick_topics(category: str, count: int) -> list[str]:
    pool = _CATEGORY_TOPICS.get(category, _CATEGORY_TOPICS["dev"])
    if count <= len(pool):
        return random.sample(pool, k=count)
    # ha többet kérünk, mint amennyi egyedi téma van, ismétléssel egészítjük ki
    return [random.choice(pool) for _ in range(count)]


class AiClient:
    def __init__(self, project: str, location: str, model: str) -> None:
        self._client = genai.Client(vertexai=True, project=project, location=location)
        self._model = model

    def _generate(self, prompt: str, response_schema: type) -> str:
        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=response_schema,
                temperature=1.0,
            ),
        )
        return response.text

    def generate_epic_with_stories(
        self,
        language: str,
        story_count: int,
        priority_names: list[str],
        topic_hint: str | None = None,
        category: str = "dev",
    ) -> EpicPlan:
        lang_name = _LANGUAGE_NAMES.get(language, language)
        category_label = _CATEGORY_LABELS.get(category, _CATEGORY_LABELS["dev"])
        topic = topic_hint or _pick_topics(category, 1)[0]
        prompt = f"""Generálj egy realisztikus {category_label} jellegű Epic-et és pontosan
{story_count} db hozzá tartozó user story-t egy Jira projekthez.

Téma / terület: {topic}

Nyelv: minden szöveges mezőt (cím, leírás, elfogadási kritériumok) {lang_name} nyelven írj.

Prioritás rangsorhoz ({len(priority_names)} szintű skála áll rendelkezésre, a listában
a legmagasabbtól a legalacsonyabbig: {", ".join(priority_names)}) minden story-hoz adj
egy priority_rank egész számot 1-től {len(priority_names)}-ig (1 = legmagasabb prioritás).

A story-k legyenek egymásra épülő, valós {category_label} munkafolyamatot tükröző elemek
(pl. dev esetén adatmodell/API előbb, UI utána, tesztelés a végén; test esetén
tesztterv/tesztkörnyezet előbb, automatizálás/végrehajtás utána; devops esetén
tervezés/IaC előbb, kiépítés/monitoring utána stb.), és jelöld reális
függőségekkel (depends_on: az adott story milyen más story indexétől függ, 0-indexelt,
csak akkor, ha tényleg logikailag szükséges). Ne hozz létre kört a függőségek között,
és legyen legalább egy story, aminek nincs függősége (ez lesz az első, amit el lehet
kezdeni). Minden story kapjon acceptance_criteria listát (3-6 elem) és story_points
Fibonacci becslést (1,2,3,5,8,13).
"""
        raw = self._generate(prompt, EpicPlan)
        return EpicPlan.model_validate_json(raw)

    def generate_standalone_tasks(
        self,
        language: str,
        count: int,
        priority_names: list[str],
        category: str = "dev",
    ) -> StandaloneTaskList:
        lang_name = _LANGUAGE_NAMES.get(language, language)
        category_label = _CATEGORY_LABELS.get(category, _CATEGORY_LABELS["dev"])
        topics = ", ".join(_pick_topics(category, min(count, 8)))
        prompt = f"""Generálj pontosan {count} db egymástól független, realisztikus
{category_label} jellegű user story-t egy Jira backlog feltöltéséhez. Lehetséges
ihlető témák (nem kötelező mindet felhasználni, variálhatsz): {topics}.

Nyelv: minden szöveges mezőt (cím, leírás, elfogadási kritériumok) {lang_name} nyelven írj.

Prioritás rangsorhoz ({len(priority_names)} szintű skála áll rendelkezésre, a listában
a legmagasabbtól a legalacsonyabbig: {", ".join(priority_names)}) minden story-hoz adj
egy priority_rank egész számot 1-től {len(priority_names)}-ig (1 = legmagasabb prioritás).

Minden story kapjon acceptance_criteria listát (3-6 elem) és story_points Fibonacci
becslést (1,2,3,5,8,13). A story-k legyenek változatosak és ne ismételjék egymást.
"""
        raw = self._generate(prompt, StandaloneTaskList)
        return StandaloneTaskList.model_validate_json(raw)
