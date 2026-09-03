"""Vékony wrapper a Jira Cloud REST (v3) és Agile (1.0) API-khoz."""

from __future__ import annotations

from typing import Any

import requests


class JiraError(RuntimeError):
    """Jira API hívás sikertelen."""


class JiraClient:
    def __init__(self, base_url: str, email: str, api_token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self._session = requests.Session()
        self._session.auth = (email, api_token)
        self._session.headers.update(
            {"Accept": "application/json", "Content-Type": "application/json"}
        )

    # -- alacsony szintű helper -------------------------------------------------

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self.base_url}{path}"
        resp = self._session.request(method, url, timeout=30, **kwargs)
        if resp.status_code >= 400:
            raise JiraError(
                f"{method} {path} -> HTTP {resp.status_code}: {resp.text[:1000]}"
            )
        if not resp.content:
            return None
        return resp.json()

    def _get(self, path: str, **kwargs: Any) -> Any:
        return self._request("GET", path, **kwargs)

    def _post(self, path: str, json_body: dict | None = None) -> Any:
        return self._request("POST", path, json=json_body)

    def _put(self, path: str, json_body: dict | None = None) -> Any:
        return self._request("PUT", path, json=json_body)

    # -- projekt / metaadat ------------------------------------------------------

    def get_current_user(self) -> dict:
        """A hitelesített Jira felhasználó adatai - kapcsolati teszthez."""
        return self._get("/rest/api/3/myself")

    def get_project(self, project_key: str) -> dict:
        return self._get(f"/rest/api/3/project/{project_key}")

    def get_issue_types_for_project(self, project_key: str) -> list[dict]:
        data = self._get(
            "/rest/api/3/issue/createmeta",
            params={
                "projectKeys": project_key,
                "expand": "projects.issuetypes",
            },
        )
        projects = data.get("projects", [])
        if not projects:
            raise JiraError(
                f"A(z) '{project_key}' projekthez nem található createmeta "
                "(nincs jogosultság vagy nem létezik a projekt)."
            )
        return projects[0].get("issuetypes", [])

    def find_issue_type_id(self, project_key: str, name_candidates: list[str]) -> str:
        issue_types = self.get_issue_types_for_project(project_key)
        lowered = {t["name"].strip().lower(): t["id"] for t in issue_types}
        for candidate in name_candidates:
            match = lowered.get(candidate.strip().lower())
            if match:
                return match
        available = ", ".join(sorted(lowered.keys()))
        raise JiraError(
            f"Egyik keresett issue type sem található a projektben ({name_candidates}). "
            f"Elérhető típusok: {available}"
        )

    def get_priorities(self) -> list[dict]:
        """A Jira instance prioritás listája, magastól az alacsony felé rendezve."""
        return self._get("/rest/api/3/priority")

    def get_fields(self) -> list[dict]:
        """A Jira instance összes mezője (system + custom), schema info-val együtt."""
        return self._get("/rest/api/3/field")

    def find_field_id(self, name_candidates: list[str], fields: list[dict] | None = None) -> str | None:
        """Mező ID keresése a megjelenített NÉV alapján (locale-/instance-függő,
        könnyen átnevezhető - ahol lehet, inkább find_field_id_by_schema-t
        használj, ami a stabil custom field type-ra illeszt)."""
        fields = fields if fields is not None else self.get_fields()
        lowered = {f["name"].strip().lower(): f["id"] for f in fields}
        for candidate in name_candidates:
            match = lowered.get(candidate.strip().lower())
            if match:
                return match
        return None

    def find_field_id_by_schema(
        self, schema_custom_keys: list[str], fields: list[dict] | None = None
    ) -> str | None:
        """Mező ID keresése a custom field STABIL schema típusa alapján
        (pl. 'com.pyxis.greenhopper.jira:gh-epic-color') - ez nem függ attól,
        hogy az adott instance-en hogyan nevezték el a mezőt."""
        fields = fields if fields is not None else self.get_fields()
        for field in fields:
            custom_type = (field.get("schema") or {}).get("custom")
            if custom_type in schema_custom_keys:
                return field["id"]
        return None

    def get_issue_link_types(self) -> list[dict]:
        data = self._get("/rest/api/3/issueLinkType")
        return data.get("issueLinkTypes", [])

    # -- board / sprint (Agile API) ----------------------------------------------

    def get_boards_for_project(self, project_key: str) -> list[dict]:
        values: list[dict] = []
        start_at = 0
        while True:
            page = self._get(
                "/rest/agile/1.0/board",
                params={"projectKeyOrId": project_key, "startAt": start_at},
            )
            values.extend(page.get("values", []))
            if page.get("isLast", True):
                break
            start_at += len(page.get("values", []))
        return values

    def get_sprints_for_board(self, board_id: int, state: str | None = None) -> list[dict]:
        params: dict[str, Any] = {}
        if state:
            params["state"] = state
        values: list[dict] = []
        start_at = 0
        while True:
            page = self._get(
                f"/rest/agile/1.0/board/{board_id}/sprint",
                params={**params, "startAt": start_at},
            )
            values.extend(page.get("values", []))
            if page.get("isLast", True):
                break
            start_at += len(page.get("values", []))
        return values

    def create_sprint(self, board_id: int, name: str, start_date: str, end_date: str) -> dict:
        return self._post(
            "/rest/agile/1.0/sprint",
            {
                "name": name,
                "originBoardId": board_id,
                "startDate": start_date,
                "endDate": end_date,
            },
        )

    def start_sprint(self, sprint_id: int, start_date: str, end_date: str) -> dict:
        return self._post(
            f"/rest/agile/1.0/sprint/{sprint_id}",
            {"state": "active", "startDate": start_date, "endDate": end_date},
        )

    def add_issues_to_sprint(self, sprint_id: int, issue_keys: list[str]) -> None:
        self._post(
            f"/rest/agile/1.0/sprint/{sprint_id}/issue",
            {"issues": issue_keys},
        )

    # -- issue CRUD ---------------------------------------------------------------

    def create_issue(self, fields: dict) -> dict:
        return self._post("/rest/api/3/issue", {"fields": fields})

    def update_issue(self, issue_key: str, fields: dict) -> None:
        self._put(f"/rest/api/3/issue/{issue_key}", {"fields": fields})

    def get_transitions(self, issue_key: str) -> list[dict]:
        data = self._get(f"/rest/api/3/issue/{issue_key}/transitions")
        return data.get("transitions", [])

    def transition_issue(self, issue_key: str, transition_id: str) -> None:
        self._post(f"/rest/api/3/issue/{issue_key}/transitions", {"transition": {"id": transition_id}})

    def create_issue_link(self, link_type_name: str, inward_key: str, outward_key: str) -> None:
        self._post(
            "/rest/api/3/issueLink",
            {
                "type": {"name": link_type_name},
                "inwardIssue": {"key": inward_key},
                "outwardIssue": {"key": outward_key},
            },
        )


def to_adf(plain_text: str) -> dict:
    """Egyszerű szöveget Atlassian Document Format (ADF) bekezdéssé alakít.

    A Jira Cloud v3 API a 'description' mezőhöz ADF-et vár, nem sima stringet.
    """
    paragraphs = [p for p in plain_text.split("\n\n") if p.strip()] or [plain_text]
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": p.strip()}],
            }
            for p in paragraphs
        ],
    }


def bullet_list_adf(items: list[str]) -> dict:
    return {
        "type": "bulletList",
        "content": [
            {
                "type": "listItem",
                "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": item}]}
                ],
            }
            for item in items
        ],
    }
