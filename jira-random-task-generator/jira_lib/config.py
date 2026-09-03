"""Konfiguráció betöltése környezeti változókból (.env is támogatott)."""

from __future__ import annotations

import os
from dataclasses import dataclass


class ConfigError(RuntimeError):
    """Hiányzó vagy hibás konfiguráció."""


def _load_dotenv_if_present() -> None:
    """Egyszerű .env betöltő (nincs extra dependency)."""
    env_path = os.path.join(os.getcwd(), ".env")
    if not os.path.isfile(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(
            f"Hiányzó környezeti változó: {name}. Lásd a README 'Konfiguráció' szakaszát."
        )
    return value


@dataclass(frozen=True)
class Config:
    jira_base_url: str
    jira_email: str
    jira_api_token: str

    gcp_project: str
    gcp_location: str
    gemini_model: str

    @classmethod
    def load(cls) -> "Config":
        _load_dotenv_if_present()
        return cls(
            jira_base_url=_require("JIRA_BASE_URL").rstrip("/"),
            jira_email=_require("JIRA_EMAIL"),
            jira_api_token=_require("JIRA_API_TOKEN"),
            gcp_project=_require("GOOGLE_CLOUD_PROJECT"),
            gcp_location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1").strip()
            or "us-central1",
            gemini_model=os.environ.get("GEMINI_MODEL", "gemini-2.5-pro").strip()
            or "gemini-2.5-pro",
        )
