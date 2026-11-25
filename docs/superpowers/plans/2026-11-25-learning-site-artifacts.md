# Learning-Site Artifacts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two queue-able artifact types — per-lecture `learning_site` and whole-book `course_learning_site` — that send a fixed "make me a site" prompt through Gemini Notebook chat, wait for the resulting Studio item, download its HTML into the course folder, and open it safely in the study workspace.

**Architecture:** A new adapter mixin talks to Gemini Notebook (chat request, Studio polling via the raw listing row, cookie-authenticated download with a Google-only host guard). A new `LearningSiteRunner` service renders the prompt from the bundled template and drives request → wait → download; `ArtifactRunner` dispatches the two types to it before its generic branches. A new HTTP route serves the untrusted HTML with a strict CSP.

**Tech Stack:** Python 3.11, FastAPI, notebooklm-py 0.8.6 (`chat.ask`, `artifacts._list_raw`), httpx, unittest, vanilla JS.

**Spec:** `docs/specs/021-learning-site-artifacts.md` (prompt template: `assets/prompts/notebook_site/learning_site.md`; raw-row fixture: `tests/fixtures/notebooklm/site_row.json`)

## Global Constraints

- TDD per core rule 16: failing test first, then minimal code; `python3 scripts/agentctl.py check` must exit 0 with zero warnings before each commit (rule 15).
- Code-review guard: file ≤ 500 lines, function ≤ 40 lines, ≤ 4 parameters (self excluded, keyword-only counted), nesting ≤ 3, every module/function/inner function has a docstring with `Args:`/`Returns:`, every module defines `logger = logging.getLogger(__name__)`.
- Layers: `entrypoints → adapters → services → domain → config`; services never import adapters. `domain/notebooklm_protocol.py` is at 494 lines — do **not** add methods there; put the new protocol in `domain/learning_site.py`.
- No `DATA_DIR` sub-path literals outside `config/` (`tests/test_settings_paths.py`).
- Tests never touch the network or Google; use fakes and the fixture.
- Commit with `python3 scripts/agentctl.py commit -m "<english message>" --type <type> --agent <name> --model <model>`; never push without the user's explicit consent.
- UI text in Traditional Chinese; web page paths are always picked, never typed (PROJECT_RULES).
- Type values: `learning_site`, `course_learning_site`; Chinese labels `學習網頁`, `整本書學習網頁`; English titles `Learning Site`, `Whole-Book Learning Site`; files `learning_site.html`, `course_learning_site.html`; usage-meter action `canvas`.
- Site Studio row: type code `10`, status `2` = generating, `3` = done; `row[1]` title, `row[15]` created `[seconds, nanos]`, `row[24] = [filename, "text/html", viewer_url, download_url, …]`.
- Timeouts: new item must appear within 300 s of sending; finished within 1800 s; poll every 20 s.
- CSP for site route (exact): `default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; media-src data: blob:; connect-src 'none'; form-action 'none'; base-uri 'none'; frame-ancestors 'self'`.

## Review Focus

- Two learning-site jobs for the same notebook running on both workers → each must get its own site, not the other's (per-notebook lock; Task 3 test `test_site_requests_are_serialized_per_notebook`).
- Gemini answers without starting a site (refusal or "quota reached" text) → job must fail or go to quota wait within 300 s, not hang 30 min (Task 4 tests `test_no_new_site_with_quota_words_raises_quota` / `..._raises_generation_error`).
- The download returns Google's sign-in page → `AuthExpiredError`, nothing written (Task 3 `test_download_rejects_sign_in_page`).
- A redirect points outside Google → refused, nothing written (Task 3 `test_download_refuses_non_google_redirect`).
- Generated site opened from the app → its scripts must not be able to call the app API (Task 5 `test_site_route_sets_strict_csp` and `test_download_route_attaches_learning_site`).

---

## File Structure

| File | Responsibility |
|---|---|
| `src/.../domain/models.py` (modify) | two `ArtifactType` members, `LEARNING_SITE_TYPES`, English titles |
| `src/.../domain/naming.py` (modify) | two `ArtifactNaming` entries (labels, example file names) |
| `src/.../domain/learning_site.py` (create) | `SiteRow`, `parse_site_row`, `LearningSiteClientProtocol`, constants |
| `src/.../services/quota_planner.py` (modify) | `("learning_site", "canvas")` action prefix |
| `src/.../services/artifact_runner.py` (modify) | `SIMPLE_OUTPUTS` file names, dispatch, skip rename |
| `src/.../services/learning_site_prompt.py` (create) | render prompt section A/B from the template |
| `src/.../services/learning_site_runner.py` (create) | request → wait → download, quota/failure mapping |
| `src/.../adapters/notebooklm/learning_sites.py` (create) | `LearningSiteMixin`: chat request, Studio polling, guarded download, per-notebook lock |
| `src/.../adapters/notebooklm/client.py` (modify) | mix `LearningSiteMixin` into `NotebookLMAdapter` |
| `src/.../entrypoints/http/artifacts.py` (modify) | `/site/` route with CSP; download route attaches learning sites |
| `src/.../entrypoints/static/studio-queue.js`, `studio-study-panels.js` (modify) | type options; study-workspace entry opening `/site/` in a new tab |
| `docs/adr/016-…`, `docs/specs/SPECS.md`, `CHANGELOG.md` | records |
| `tests/test_learning_site.py` (create) | all tests below |

---

### Task 1: Artifact types, names, quota action

**Files:**
- Modify: `src/notebooklm_batch_studio/domain/models.py`, `domain/naming.py`, `services/quota_planner.py`, `services/artifact_runner.py` (only `SIMPLE_OUTPUTS`), `entrypoints/static/studio-queue.js`
- Test: `tests/test_learning_site.py::TypesTest`

**Interfaces:**
- Produces: `ArtifactType.LEARNING_SITE`, `ArtifactType.COURSE_LEARNING_SITE`; `LEARNING_SITE_TYPES: tuple[ArtifactType, ...]` in `domain/models.py` (domain, so `job_planner` and `artifact_runner` can both import it without a cycle); `SIMPLE_OUTPUTS[...] = ("learning_site", "learning_site.html", "course_learning_site.html")` for both types (reused by `adopt_outputs`, which then recognises the files with no further change).

- [ ] **Step 1: Write the failing test**

```python
class TypesTest(unittest.TestCase):
    def test_types_labels_files_quota_and_ui(self) -> None:
        self.assertEqual(ArtifactType.LEARNING_SITE.value, "learning_site")
        self.assertEqual(ArtifactType.COURSE_LEARNING_SITE.value, "course_learning_site")
        self.assertEqual(label_for("learning_site"), "學習網頁")
        self.assertEqual(label_for("course_learning_site"), "整本書學習網頁")
        self.assertEqual(get_artifact_english_title(ArtifactType.LEARNING_SITE, "[L01]"), "[L01] Learning Site")
        self.assertEqual(action_kind_for(ArtifactType.COURSE_LEARNING_SITE), "canvas")
        self.assertEqual(SIMPLE_OUTPUTS[ArtifactType.LEARNING_SITE][1:], ("learning_site.html", "course_learning_site.html"))
        self.assertIn("course_learning_site", COURSE_TYPES)
        js = (STATIC / "studio-queue.js").read_text(encoding="utf-8")
        self.assertIn("{ value: 'learning_site', label: '學習網頁' }", js)
        self.assertIn("{ value: 'course_learning_site', label: '整本書學習網頁' }", js)
```

(`COURSE_TYPES` from `services/course_settings.py`; check `get_artifact_english_title`'s real prefix format in `domain/models.py:334` and adjust the expected string to it.)

- [ ] **Step 2: Run** `uv run python -m unittest tests.test_learning_site.TypesTest` — expect `AttributeError: LEARNING_SITE`.
- [ ] **Step 3: Implement** the enum members (after `VIDEO` / `COURSE_VIDEO`), `ENGLISH_ARTIFACT_TITLES` entries, two `ArtifactNaming(...)` rows (descriptions: 「互動＋視覺化的單講學習網頁（Gemini Notebook 產生）」／「整本書的互動學習網頁」; examples `learning_site.html` / `course_learning_site.html`), `("learning_site", "canvas")` in `_ACTION_PREFIXES`, the `SIMPLE_OUTPUTS` rows and `LEARNING_SITE_TYPES`, and the two JS options (lecture list after `video`, course list after `course_video`).
- [ ] **Step 4: Run** the test, then `uv run python -m unittest tests.test_adopt_outputs tests.test_versions_and_options` — expect OK.
- [ ] **Step 5: Commit** `feat(types): add learning_site and course_learning_site artifact types`.

---

### Task 2: Prompt rendering

**Files:**
- Create: `src/notebooklm_batch_studio/services/learning_site_prompt.py`
- Modify: `src/notebooklm_batch_studio/services/job_planner.py` (site jobs get `custom_prompt=None`)
- Test: `tests/test_learning_site.py::PromptTest`

**Interfaces:**
- Produces: `render_site_prompt(course: Course, lecture: Lecture | None, extra: str | None = None, template: Path = DEFAULT_TEMPLATE) -> str`; `DEFAULT_TEMPLATE = PROJECT_ROOT / "assets/prompts/notebook_site/learning_site.md"` (locate `PROJECT_ROOT` the same way `services/notes/module_prompts.py` does); `SITE_TRIGGER = "make me a site"`; `DEFAULT_READER = "修這門課的學生，準備考試，並希望把概念用在實務"`.

- [ ] **Step 1: Write the failing tests**

```python
class PromptTest(unittest.TestCase):
    def test_chapter_prompt_fills_section_a(self) -> None:
        text = render_site_prompt(course, lecture1)          # lecture1: no=1, topic="Career-Counseling-A-Life"
        self.assertTrue(text.startswith("make me a site"))
        self.assertIn("「生涯諮商與實務」第 1 講「Career Counseling A Life」", text)
        self.assertNotIn("{{", text)
        self.assertNotIn("整本書的互動學習網頁", text)
    def test_book_prompt_uses_section_b_with_range(self) -> None:
        text = render_site_prompt(course, None)               # lectures 1–6, 13, 14, 16, 17
        self.assertIn("整本書的互動學習網頁", text)
        self.assertIn("第 1–17 講（共 10 講）", text)
    def test_extra_instructions_are_appended(self) -> None:
        self.assertTrue(render_site_prompt(course, lecture1, extra="多舉諮商實例").rstrip().endswith("補充要求：多舉諮商實例"))
    def test_full_custom_prompt_is_used_verbatim(self) -> None:
        custom = "make me a site\n只做 3 題測驗"
        self.assertEqual(render_site_prompt(course, lecture1, extra=custom), custom)
    def test_planned_site_jobs_have_no_generic_prompt(self) -> None:
        # job_planner otherwise stores PromptGenerator's generic fallback "請為【…】生成高品質學術產出物。",
        # which the runner would append as 補充要求
        course = replace(course, selected_chapter_artifacts=["learning_site"], selected_course_artifacts=["course_learning_site"])
        jobs = generate_jobs_for_course(course)
        self.assertTrue(jobs)
        self.assertTrue(all(j.custom_prompt is None for j in jobs))
```

(Check the real type of `selected_chapter_artifacts` in `domain/models.py` — list or comma string — and build the course accordingly.)

- [ ] **Step 2: Run** — expect `ModuleNotFoundError`.
- [ ] **Step 3: Implement.** Section A = text after `## A. 單一章節版` up to the next line `---`; section B = text after `## B. 整本書／整門課版`. Topic: replace `-`/`_` with spaces. Book range `第 {min}–{max} 講（共 {n} 講）`. Reader = `DEFAULT_READER`. Rule for `extra`: starts with `SITE_TRIGGER` → return it unchanged; non-empty → append `\n\n補充要求：{extra}`. In `job_planner`, pass `custom_prompt=None` (instead of the blueprint) when `art_type in LEARNING_SITE_TYPES` — at both the custom-selection and profile call sites (`services/job_planner.py:120-126` and `:150-160`).
- [ ] **Step 4: Run** — expect OK.
- [ ] **Step 5: Commit** `feat(site): render learning-site prompts from the bundled template`.

---

### Task 3: Adapter — request, Studio polling, guarded download

**Files:**
- Create: `src/notebooklm_batch_studio/domain/learning_site.py`, `src/notebooklm_batch_studio/adapters/notebooklm/learning_sites.py`
- Modify: `src/notebooklm_batch_studio/adapters/notebooklm/client.py` (add `LearningSiteMixin` to the base list)
- Test: `tests/test_learning_site.py::RowParsingTest`, `::AdapterTest`

**Interfaces:**
- Produces (domain): `SITE_TYPE_CODE = 10`; `SiteRow(id: str, title: str, status: int, created: float, filename: str, download_url: str)` frozen dataclass; `parse_site_row(row: list[Any]) -> SiteRow | None` (None unless type 10 and `row[24][1] == "text/html"`); `LearningSiteClientProtocol` with `list_site_rows(notebook_id: str) -> list[SiteRow]`, `request_site(notebook_id: str, prompt: str, source_ids: list[str]) -> str` (chat answer), `download_site(row: SiteRow, output_path: str) -> None`, and `site_lock(notebook_id: str) -> asyncio.Lock`.
- Produces (adapter): `LearningSiteMixin` implementing the protocol on `NotebookLMAdapter`; uses `client.artifacts._list_raw` and `client.chat.ask`; download uses the storage-state cookies for `google.com` domains, `httpx` with `follow_redirects=False`, at most 6 hops, hosts must end with `.google.com` or `.googleusercontent.com`.

- [ ] **Step 1: Write the failing tests**

```python
class RowParsingTest(unittest.TestCase):
    def test_parses_fixture_row(self) -> None:
        row = json.loads((FIXTURES / "notebooklm" / "site_row.json").read_text(encoding="utf-8"))
        site = parse_site_row(row)
        self.assertEqual((site.status, site.filename), (3, "生涯諮商：生命生涯發展觀點_互動學習網頁.html"))
        self.assertTrue(site.download_url.startswith("https://contribution.usercontent.google.com/"))
    def test_non_site_rows_are_ignored(self) -> None:
        self.assertIsNone(parse_site_row(["id", "quiz", 4, [], 3]))

class AdapterTest(unittest.IsolatedAsyncioTestCase):
    async def test_download_refuses_non_google_redirect(self) -> None: ...   # MockTransport: 302 -> https://evil.example/x ; assert raises ValueError and file absent
    async def test_download_rejects_sign_in_page(self) -> None: ...          # 200 text/html containing "accounts.google.com/ServiceLogin" ; assert AuthExpiredError, file absent
    async def test_download_writes_html_atomically(self) -> None: ...        # 200 "<!doctype html><title>x</title>" ; file content equal, no ".part" left
    async def test_site_requests_are_serialized_per_notebook(self) -> None:  # same notebook -> same Lock object; different notebook -> different
```

(Make the HTTP layer injectable: `_site_http_client(self) -> httpx.AsyncClient` method that tests override to use `httpx.MockTransport`.)

- [ ] **Step 2: Run** — expect import errors.
- [ ] **Step 3: Implement** `domain/learning_site.py` and the mixin. Sign-in detection: final URL host `accounts.google.com`, or body contains `accounts.google.com/ServiceLogin` or `<title>Sign in`. Write to `<dest>.part` then `os.replace`. Locks: `dict[str, asyncio.Lock]` created lazily on the adapter instance.
- [ ] **Step 4: Run** the tests and `python3 scripts/agentctl.py check`.
- [ ] **Step 5: Commit** `feat(adapter): request, poll and download Gemini Notebook learning sites`.

---

### Task 4: Runner and dispatch

**Files:**
- Create: `src/notebooklm_batch_studio/services/learning_site_runner.py`
- Modify: `src/notebooklm_batch_studio/services/artifact_runner.py`
- Test: `tests/test_learning_site.py::RunnerTest`

**Interfaces:**
- Consumes: `render_site_prompt` (Task 2), `LearningSiteClientProtocol`/`SiteRow` (Task 3), `versioned_name` (`domain/naming.py`), `JobTarget`/`ProcessResult` (`services/quiz_runner.py`).
- Produces: `LearningSiteRunner(client: LearningSiteClientProtocol, clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], Awaitable[None]] = asyncio.sleep)`; `async process(job: ArtifactJob, course: Course, target: JobTarget) -> ProcessResult`; constants `APPEAR_SECONDS = 300`, `FINISH_SECONDS = 1800`, `POLL_SECONDS = 20`, `QUOTA_WORDS = ("額度", "上限", "quota", "limit")`. `ArtifactRunner` gains `self.site_runner` and dispatches `LEARNING_SITE_TYPES` **before** the `SIMPLE_OUTPUTS` branch, and skips `rename_after_generation` for those types.

- [ ] **Step 1: Write the failing tests** (fake client with scripted `list_site_rows` results and a fake clock/sleep):

```python
async def test_downloads_new_site_to_versioned_file(self) -> None
    # before: one existing site id; after request: a new row status 2 then 3
    # assert path == target.out_dir / "learning_site_v2.html" for job.version == 2, ids == [new_id],
    # request_site called with target.source_ids and a prompt starting "make me a site"
async def test_no_new_site_with_quota_words_raises_quota(self) -> None
    # chat answer "目前已達使用上限" and no new row for > APPEAR_SECONDS -> QuotaExceededError
async def test_no_new_site_raises_generation_error(self) -> None
    # chat answer "我無法建立網站" -> RuntimeError whose message contains the answer
async def test_failed_status_raises(self) -> None
    # new row with status 4 -> RuntimeError
async def test_artifact_runner_dispatches_and_skips_rename(self) -> None
    # ArtifactRunner.process_job_with_ids for LEARNING_SITE uses site_runner; rename_artifact not called
```

- [ ] **Step 2: Run** — expect `ModuleNotFoundError`.
- [ ] **Step 3: Implement.** Under `client.site_lock(target.nb_id)`: snapshot ids → `request_site` → poll until a row whose id is new and `created` is newest appears (else after `APPEAR_SECONDS` raise quota/generation error per `QUOTA_WORDS`) → poll until status 3 (status not in {2, 3} → `RuntimeError`; exceeding `FINISH_SECONDS` → `RuntimeError`) → `download_site` to `target.out_dir / versioned_name(file, job.version)` where `file` comes from `SIMPLE_OUTPUTS` (lecture vs course). Prompt: `render_site_prompt(course, lecture_or_None, extra=job.custom_prompt)`.
- [ ] **Step 4: Run** the tests, `uv run python -m unittest discover -s tests`, and `agentctl check`.
- [ ] **Step 5: Commit** `feat(site): queue learning-site jobs through LearningSiteRunner`.

---

### Task 5: Safe viewing and web entry

**Files:**
- Modify: `src/notebooklm_batch_studio/entrypoints/http/artifacts.py`, `entrypoints/static/studio-study-panels.js` (and `studio-shell.js` if the tile list lives there)
- Create: `docs/adr/016-untrusted-learning-site-html.md` via `python3 .agents/skills/adr-issue-tracker/scripts/tracker_cli.py --add-adr untrusted-learning-site-html --title ...`
- Test: `tests/test_learning_site.py::ViewTest`

**Interfaces:**
- Produces: `GET /api/artifacts/{code}/site/{file_path:path}` (operation_id `view_learning_site`) returning the file as `text/html; charset=utf-8` with the exact CSP from Global Constraints plus `X-Content-Type-Options: nosniff` and `Referrer-Policy: no-referrer`; 415 for non-`.html`; same traversal rules as the download route (`_resolve_artifact_path`). The download route serves any file whose name starts with `learning_site` or `course_learning_site` as `attachment`.

- [ ] **Step 1: Write the failing tests**

```python
def test_site_route_sets_strict_csp(self) -> None
    # write <course>/03 Notes/NotebookLM/01_x/learning_site.html; GET /api/artifacts/{code}/site/01_x/learning_site.html
    # assert 200, header CSP == exact string, "connect-src 'none'" in it
def test_site_route_rejects_non_html_and_traversal(self) -> None   # .png -> 415 ; ../../x.html -> 403
def test_download_route_attaches_learning_site(self) -> None       # content-disposition starts with "attachment"
def test_study_panel_opens_site_route(self) -> None                # studio-study-panels.js contains "/site/" and "學習網頁"
```

- [ ] **Step 2: Run** — expect 404 / assertion failures.
- [ ] **Step 3: Implement** the route and the attachment rule; add a 「學習網頁」 entry in the study workspace (lecture scope `learning_site`, course scope `course_learning_site`) that opens the newest done version via `/api/artifacts/{code}/site/{rel_path}` in a new tab (`window.open(url, '_blank', 'noopener')`). Write ADR-016 (decision: serve with strict CSP on the app origin; localStorage is shared with the app's non-secret UI prefs — accepted; alternative of a separate origin rejected as heavier).
- [ ] **Step 4: Run** tests, full suite, `agentctl check`; browser check on 127.0.0.1:8768 with a hand-placed sample `learning_site.html` (copy of the 2026-11-25 test site) under a temp `DATA_DIR`, confirming the page loads, sliders work, and `fetch('/api/status')` from its console is blocked by CSP.
- [ ] **Step 5: Commit** `feat(web): open learning sites through a CSP-restricted route`.

---

### Task 6: Records and real-data acceptance

**Files:** `docs/specs/021-learning-site-artifacts.md` (status → Implemented, tick acceptance), `docs/specs/SPECS.md` (row), `CHANGELOG.md` (via commit), `docs/standards/PROJECT_RULES.md` (add the two types to the 產出 list), `.agents/tasks/TASK-040-*.json` (done).

- [ ] **Step 1:** Update the docs above; `agentctl check` exit 0; commit `docs(site): record SPEC-021 implementation`.
- [ ] **Step 2 (needs the user's go-ahead — uses Gemini Notebook quota):** on 生涯諮商與實務, enable `learning_site` for lecture 1 only, let the queue run, then verify: file at `study/115-1/CP__31000-生涯諮商與實務/03 Notes/NotebookLM/01_…/learning_site.html`, job `done`, opened via the study workspace with no console errors.
- [ ] **Step 3:** Report results; do not push without consent.

---

## Not in this plan (other unfinished items from 2026-11-25)

| Item | Status / what is needed |
|---|---|
| Push local commits `5c6ac66`, `2f23fe8`, `7e7aa65`, `dae1dcd` (+ this plan) | waiting for the user's consent |
| "Playwright 常被擋" — move the literature browser (and possibly Gemini Notebook login) to the real-Chrome + CDP approach already used for Gemini web | user has not said which sign-in is blocked; separate plan once known |
| Real-world check of Gemini note quota resume (SPEC-020) | happens the next time Gemini's limit is actually hit |
| TASK-036 manual checks (#1, #3–#7, #9, #12–#16, #19–#21) | user, see `.agents/tasks/TASK-036-checklist.md` |
| Deprecate `migrate-study-layout` (risk shown by ISSUE-069) | proposal only; user has not decided |
| Gemini Notebook test site generated on 2026-11-25 for 生涯諮商與實務 ch1 | in Studio and in the scratchpad only; after Task 4 it can be re-fetched by the queue, or placed as `learning_site.html` and adopted with 「從既有檔案建立產出紀錄」 |
