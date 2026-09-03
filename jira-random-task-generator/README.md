# jira-random-task-generator

AI-alapú (Vertex AI / Gemini) random Jira task generátor. Egy megadott Jira
Cloud projektbe (mindig **Scrum** módban) generál realisztikus tartalmú
task-okat, és be is állítja hozzá a szükséges sprint-infrastruktúrát.

Konfigurálható:

- **hány task** készüljön (`--count`; `--type epic` esetén ez az epicek
  száma, `--stories-per-epic` pedig az epicenkénti story-k száma)
- **milyen nyelven** (magyar vagy angol, `--language`)
- **milyen típusú** (`--type epic` vagy `--type story`)
  - `epic` esetén a tool `--count` db Epicet generál, mindegyiket
    `--stories-per-epic` db user story-ra bontja, elvégzi a
    **prioritizálást**, a **függőségek** (blocks/is blocked by linkek)
    felállítását és a **start/due date**-ek kiosztását a story-k egymásra
    épülése alapján
  - **több epic esetén az epicek időablakai egymást átfedik, de sosem
    ugyanakkor indulnak** — valóságot szimulálva (lásd lentebb)
  - epicenként az AI által meghatározott, függőség nélküli **első elem**
    "In Progress" státuszba kerül és bekerül az **aktuális sprintbe**, a
    többi a **backlogban** marad
- **az első elem típusa** epicenként: hagyományos **Story**, **Spike** vagy
  **POC** (`--first-story-type`)
- **kategória**: `dev` (fejlesztési), `test` (tesztelési/QA) vagy `devops`
  jellegű tartalom (`--category`) — ez irányítja az AI témaválasztását és a
  létrehozott issue-k `labels` mezőjét is
- **sprint állapot**: a projekt mindig Scrum módban dolgozik; ha nincs futó
  sprint a Scrum boardon, a tool létrehoz és elindít egyet

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
kezeléshez (sprint create/start). A projekthez már léteznie kell egy
**Scrum** boardnak (lásd Korlátok).

## Használat

```bash
# 5 önálló user story angolul, DevOps kategóriában, sima backlog issue-ként
uv run generate-jira-tasks -p DEMO -c 5 -l en -t story -k devops

# 3 epic, epicenként 5 story-val, magyarul: prioritás, függőségek, dátumok,
# egymást átfedő epic-időablakok, sprint
uv run generate-jira-tasks -p DEMO -c 3 -s 5 -l hu -t epic

# Terv kiírása Jira-módosítás nélkül (nem hív írás jellegű API-t)
uv run generate-jira-tasks -p DEMO -c 3 -t epic -d

# Epicenként az első elem Spike legyen sima Story helyett
uv run generate-jira-tasks -p DEMO -c 2 -t epic -f spike

# Témajavaslat megadása az AI-nak, egyedi issue type nevekkel
uv run generate-jira-tasks -p DEMO -c 2 -t epic \
  -o "fizetési szolgáltató integráció" \
  -E "Epic" -S "Történet"
```

(Minden kapcsolónak van hosszú és rövid formája is, lásd lentebb.)

### CLI kapcsolók

| Kapcsoló | Rövid | Default | Leírás |
|---|---|---|---|
| `--project` | `-p` | *(kötelező)* | Jira projekt kulcs |
| `--count` | `-c` | `5` | `type=story`: hány önálló story; `type=epic`: hány epic |
| `--stories-per-epic` | `-s` | `4` | Epicenként hány user story (csak `type=epic` esetén) |
| `--language` | `-l` | `hu` | `hu` vagy `en` |
| `--type` | `-t` | `story` | `epic` vagy `story` |
| `--category` | `-k` | `dev` | `dev` (fejlesztési), `test` (tesztelési) vagy `devops` |
| `--first-story-type` | `-f` | `story` | Epicenként az első elem típusa: `story`, `spike` vagy `poc` |
| `--topic` | `-o` | *(AI választ)* | Opcionális témajavaslat |
| `--epic-issue-type` | `-E` | auto-detektált | Issue type név felülírás, ha az instance-en nem "Epic" a név |
| `--story-issue-type` | `-S` | auto-detektált | Issue type név felülírás, ha az instance-en nem "Story" a név |
| `--dry-run` | `-d` | ki | Csak a generált tervet írja ki, Jira-ba nem ír |

## Működési logika

1. Projekt, issue type-ok (Epic/Story, opcionálisan Spike/POC), priority
   lista és a "Start date" mező lekérdezése a Jira instance-ről
   (auto-detektálva, nem hardcode-olva).
2. A projekt Scrum boardjának keresése; ha nincs futó sprint, a tool
   létrehoz egy 2 hetes sprintet és elindítja.
3. `--type epic` esetén `--count` db epic AI-generálása (mindegyik
   `--stories-per-epic` db story-val): epic cím/leírás + story-k (cím,
   leírás, elfogadási kritériumok, story point, prioritás-rang,
   függőségek), a `--category` alapján tematizálva (dev/test/devops).
4. **Epic-időablakok szétosztása**: minden epic egy ~1-2 hetes, véletlenszerű
   hosszúságú időablakot kap; a következő epic mindig néhány nappal
   (véletlenszerűen, de sosem 0 nappal) később indul, mint az előző — így az
   epicek munkája jellemzően **időben átfedésbe kerül** egymással anélkül,
   hogy ugyanazon a napon indulnának (valóságot szimulálva: a csapat több
   epicen dolgozik párhuzamosan, csúsztatott indulással).
5. Epiconként a tool a függőség-gráfot ciklusmentesíti és topológiai
   sorrendbe rendezi, ez alapján osztja ki a story-k start/due dátumait a
   saját epic-időablakán belül.
6. Jira-ban létrejön minden Epic, majd alattuk a story-k (`parent` mezővel
   az Epichez kötve, `labels` mezőben a kategóriával), rájuk a
   `Blocks`/`is blocked by` linkek a függőségek alapján.
7. Epiconként a függőség nélküli, topológiailag legelső elem — típusa a
   `--first-story-type` szerint Story/Spike/POC — bekerül az aktuális
   sprintbe és át lesz állítva "In Progress"-re; a többi a backlogban marad
   alapértelmezett ("To Do") státuszban.

## Korlátok, amikről tudni kell

- **Csak Scrum**: a tool feltételezi, hogy a projekt Scrum módban dolgozik,
  és a projekthez tartozik (vagy létrehozható) egy Scrum board. A Jira
  Cloud API nem támogatja egy meglévő board típusának (kanban → scrum)
  API-n keresztüli átalakítását — ha a projekthez nincs Scrum board, a tool
  figyelmeztet és sprint-kezelés nélkül, sima backlog issue-ként hozza létre
  a task-okat (ilyenkor hozz létre egy Scrum boardot a Jira felületén).
- **Spike/POC issue type**: ha a `--first-story-type spike` vagy `poc`
  kapcsolót használod, de a projektben nincs ilyen nevű issue type
  konfigurálva, a tool figyelmeztet és helyette sima Story-t hoz létre.
- **Egyetlen aktuális sprint**: mivel Jira-ban egyszerre csak egy sprint
  lehet aktív egy boardon, minden epic első eleme ugyanabba az aktuális
  sprintbe kerül (ez realisztikus: egy sprinten belül több, egymást átfedő
  epic munkája is zajlik egyszerre) — az epicek saját start/due dátumai
  ettől függetlenül elhúzódhatnak a sprint végén túlra is.
- **Egyedi mezők**: a "Start date" mező neve és elérhetősége instance-enként
  eltér (Advanced Roadmaps / egyedi field konfiguráció). Ha nem található,
  a tool csak a `duedate`-et állítja be és figyelmeztet.
- **Opcionális mezők hiba-tűrése**: minden issue előbb a kötelező mezőkkel
  (project, issue type, summary, description) jön létre, az opcionális
  mezőket (priority, duedate, parent, labels, start date) utólag,
  egyenként állítja be — ha valamelyik a screen-konfiguráció miatt nem
  elérhető, a tool figyelmeztetést ír, de nem áll le.
- A tool **csak létező projektet konfigurál** (sprintek, board-detektálás);
  új Jira projektet nem hoz létre.
- Ez az eszköz élő Jira/Vertex AI hitelesítő adatok nélkül készült, éles
  instance-en még nem lett tesztelve — első futtatás előtt érdemes
  `--dry-run`-nal ellenőrizni a generált tervet, utána egy teszt projekten
  kipróbálni.
