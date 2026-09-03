# jira-random-task-generator

AI-alapú (Vertex AI / Gemini) random Jira task generátor. Egy megadott Jira
Cloud projektbe generál realisztikus tartalmú task-okat, és be is állítja
hozzá a szükséges sprint-infrastruktúrát.

Konfigurálható:

- **hány task** készüljön (`--count`)
- **milyen nyelven** (magyar vagy angol, `--language`)
- **milyen típusú** (`--type epic` vagy `--type story`)
  - `epic` esetén a tool egy Epicet generál, azt `--count` db user story-ra
    bontja, elvégzi a **prioritizálást**, a **függőségek** (blocks/is blocked
    by linkek) felállítását és a **start/due date**-ek kiosztását a story-k
    egymásra épülése alapján
  - epic esetén az AI által meghatározott, függőség nélküli **első story**
    "In Progress" státuszba kerül és bekerül az **aktuális sprintbe**, a
    többi a **backlogban** marad
- **board/sprint állapot**: ha nincs futó sprint a scrum boardon, a tool
  létrehoz és elindít egyet

## Telepítés (uv)

```bash
cd jira-random-task-generator

uv venv
uv sync
```

Futtatás: `uv run generate-jira-tasks ...` (vagy `uv run python generate_tasks.py ...`).

## Konfiguráció

A tool környezeti változókból olvassa a beállításokat (vagy egy `.env`
fájlból a munkakönyvtárban, `KULCS=érték` formátumban):

| Változó | Kötelező | Leírás |
|---|---|---|
| `JIRA_BASE_URL` | igen | pl. `https://yourcompany.atlassian.net` |
| `JIRA_EMAIL` | igen | Jira account email |
| `JIRA_API_TOKEN` | igen | [Atlassian API token](https://id.atlassian.com/manage-profile/security/api-tokens) |
| `GOOGLE_CLOUD_PROJECT` | igen | GCP projekt ID (Vertex AI-hoz) |
| `GOOGLE_CLOUD_LOCATION` | nem | Vertex AI régió (default: `us-central1`) |
| `GEMINI_MODEL` | nem | Gemini modell név (default: `gemini-2.5-pro`) |

A Vertex AI hívásokhoz szabványos Google Application Default Credentials
(ADC) szükséges: `gcloud auth application-default login`, vagy
`GOOGLE_APPLICATION_CREDENTIALS` egy service account JSON-ra mutatva. A
service accountnak `Vertex AI User` szerepkör kell.

A Jira felhasználónak jogosultnak kell lennie a célprojektben issue-k
létrehozására, a project adminisztrátorának pedig a board/sprint
kezeléshez (sprint create/start).

## Használat

```bash
# 5 önálló user story angolul, sima backlog issue-ként
uv run generate-jira-tasks --project DEMO --count 5 --language en --type story

# Epic + 6 user story magyarul: prioritás, függőségek, dátumok, sprint
uv run generate-jira-tasks --project DEMO --count 6 --language hu --type epic

# Terv kiírása Jira-módosítás nélkül (nem hív írás jellegű API-t)
uv run generate-jira-tasks --project DEMO --count 6 --type epic --dry-run

# Témajavaslat megadása az AI-nak, egyedi issue type nevekkel
uv run generate-jira-tasks --project DEMO --count 4 --type epic \
  --topic "fizetési szolgáltató integráció" \
  --epic-issue-type "Epic" --story-issue-type "Történet"
```

### CLI kapcsolók

| Kapcsoló | Default | Leírás |
|---|---|---|
| `--project`, `-p` | *(kötelező)* | Jira projekt kulcs |
| `--count`, `-c` | `5` | Hány story (ill. epic esetén hány story az epic alatt) |
| `--language`, `-l` | `hu` | `hu` vagy `en` |
| `--type`, `-t` | `story` | `epic` vagy `story` |
| `--board-type` | epic→`scrum`, story→`kanban` | Board/sprint kezelés módja |
| `--topic` | *(AI választ)* | Opcionális témajavaslat |
| `--epic-issue-type` / `--story-issue-type` | auto-detektált | Issue type név felülírás, ha az instance-en nem "Epic"/"Story" a név |
| `--dry-run` | ki | Csak a generált tervet írja ki, Jira-ba nem ír |

## Működési logika

1. Projekt, issue type-ok (Epic/Story), priority lista és a "Start date" mező
   lekérdezése a Jira instance-ről (auto-detektálva, nem hardcode-olva).
2. `--type epic` esetén: a projekt boardjai közül scrum board keresése; ha
   nincs futó sprint, a tool létrehoz egy 2 hetes sprintet és elindítja.
3. AI (Gemini, Vertex AI, strukturált JSON response schema-val) generálja a
   tartalmat: epic cím/leírás + N story (cím, leírás, elfogadási
   kritériumok, story point, prioritás-rang, függőségek).
4. A tool a függőség-gráfot ciklusmentesíti és topológiai sorrendbe rendezi,
   ez alapján osztja ki a start/due dátumokat a sprint (vagy egy 1-2 hetes
   ablak) időkeretén belül.
5. Jira-ban létrejön az Epic, majd a story-k (`parent` mezővel az Epichez
   kötve), rájuk a `Blocks`/`is blocked by` linkek a függőségek alapján.
6. A függőség nélküli, topológiailag legelső story bekerül az aktuális
   sprintbe és át lesz állítva "In Progress"-re; a többi a backlogban marad
   alapértelmezett ("To Do") státuszban.

## Korlátok, amikről tudni kell

- **Board típus váltás**: a Jira Cloud API nem támogatja egy meglévő projekt
  board-típusának (kanban ⇄ scrum) API-n keresztüli átalakítását. A tool
  ezért a projekthez *már létező* boardot használja a kért típusban; ha
  nincs ilyen, figyelmeztet és sprint-kezelés nélkül, sima issue-ként hozza
  létre a task-okat.
- **Egyedi mezők**: a "Start date" mező neve és elérhetősége instance-enként
  eltér (Advanced Roadmaps / egyedi field konfiguráció). Ha nem található,
  a tool csak a `duedate`-et állítja be és figyelmeztet.
- **Opcionális mezők hiba-tűrése**: minden issue előbb a kötelező mezőkkel
  (project, issue type, summary, description) jön létre, az opcionális
  mezőket (priority, duedate, parent, start date) utólag, egyenként állítja
  be — ha valamelyik a screen-konfiguráció miatt nem elérhető, a tool
  figyelmeztetést ír, de nem áll le.
- A tool **csak létező projektet konfigurál** (sprintek, board-detektálás);
  új Jira projektet nem hoz létre.
- Ez az eszköz élő Jira/Vertex AI hitelesítő adatok nélkül készült, éles
  instance-en még nem lett tesztelve — első futtatás előtt érdemes
  `--dry-run`-nal ellenőrizni a generált tervet, utána egy teszt projekten
  kipróbálni.
