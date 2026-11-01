# Changelog

All notable changes to **notebooklm-batch-studio** are documented here
(format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versions: [SemVer](https://semver.org/)).

## [Unreleased]

### Added
- docs(specs): add SPEC-009 for Study Studio UI Redesign, 9-tool matrix, dedicated customize tab, luxury turntable, and avatar customization (ADR-007) (by `@antigravity`)
- feat(skills): add design-psychology-master cognitive audit tool (by `@antigravity`)
- docs(archive): preserve Version 1 through Version 4 standalone prototypes and index map in designs_archive/ (by `@antigravity`)
- docs(midterm): complete midterm project deliverables in DATA_DIR/midterm-submission/ including 9-page report (docx/pdf), 12-slide presentation with speaker notes (pptx/pdf), AI collaboration summary (md/pdf), and 1440x900 walkthrough video with clean subtitles (mp4) (by `@antigravity`)
- feat(study,mcp): add student study portal MCP tools, spaced repetition weakness tracking, and remote sync tools (TASK-007) (by `@antigravity`)
- feat(spike): scaffold notebooklm spike script, sample pdf generator, and standard DATA_DIR paths (TASK-001) (`TASK-001`, by `@antigravity`)
- feat(domain,queue): implement course domain models, sqlite queue repository, course parser, and parallel worker pool (TASK-002) (`TASK-002`, by `@antigravity`)
- feat(adapter,converters): implement notebooklm adapter and quiz, flashcard, and mindmap converters (TASK-003) (by `@antigravity`)
- feat(orchestrator,cli): implement batch service, watcher, reporter, and cli subcommands (TASK-004) (by `@antigravity`)
- feat(api,mcp,web): implement FastAPI web UI, OpenAPI routes, and MCP server (TASK-005) (by `@antigravity`)
- feat: enhance course folder and chapter regex parsing (by `@antigravity`)
- feat: support in-app English renaming, 9 artifact types, and dual-column Web dashboard matrix (by `@antigravity`)
- feat(adapters/domain): add adapters/domain module (by `@antigravity`)
- feat(adapters/domain): add adapters/domain module (by `@antigravity`)
- feat(adapters/domain): update adapters/domain (by `@antigravity`)
- feat(adapters/domain): add adapters/domain module (by `@antigravity`)
- feat(studio): rename mind maps, versioned regeneration, per-course generation options with device-sized infographics, naming guide, live web status and auto-resume (by `@claude-code`)
- feat(studio): usage guide page, concept-explanation reports, rendered report HTML, saved artifact selections, isolated CLI tests, and split adapter downloads (by `@claude-code`)
- feat(studio): folder picker, change artifact types after adding, study-portal viewers, browser login, numbered quiz batches, 30-question subject-neutral prompts, weekly quota, and report instructions fix (by `@claude-code`)
- feat(settings): course-wide extra instructions, editable language and mock exam size, quiz difficulty, custom video style, and per-output settings (SPEC-006) (by `@claude-code`)
- feat(settings): real per-quiz question count (default 30) driving prompt, check and NotebookLM size; mock exam prompt follows its count; defaults marked in the web app with a reset button (by `@claude-code`)
- feat(courses): settings when adding, per-course pause/start, chapter range for course-wide outputs, delete course, reuse existing notebook; fix study-portal quizzes; split oversized modules (by `@claude-code`)
- feat(study): study plan with next step and exam countdown, progress marks, spaced review schedule, grounded answer explanations, chapter tags for course exams, editable exam date (by `@claude-code`)
- feat(web): student experience - Today plan, in-page quiz review with retry-wrong and NotebookLM explanations, spaced flashcard review, mock-exam timer, audio resume, add-course wizard, grouped course page, toasts, light theme and iPad layout (by `@claude-code`)
- feat: rename NotebookLM to Gemini Notebook in all user-facing text and links (ADR-006); start-up port check names the owner of a busy port; one-click macOS launcher app opening a full-screen Chrome app window; focus button and web app manifest; split course-settings MCP tools out of mcp_server (by `@claude-code`)
- feat(web): design v2 preview (?design=v2) - dark base with purple accent, lecture colour cues, soft cards, gradient progress, reduced-motion support; chapter chips wrap on phones (by `@claude-code`)
- feat(web): design v2 is the default look (?design=v1 brings back the old one) (by `@claude-code`)
- feat(learning): lecture PDF reader route (read-only, folder-confined), key points asked once and saved, forgetting-curve memory strength, study streak and heatmap, Socratic tutor that continues one conversation, confidence ratings on quiz attempts and mistakes; HTTP + MCP (by `@claude-code`)
- feat(web): learning aids UI - course reader (pdf.js 4.10.38 vendored) with colour-coded key points, memory strength / streak / heatmap on Today, resume where you stopped, confidence ratings with sure-but-wrong feedback, peak-end comparison, mixed review, recall-first mode, flashcard answer box, pomodoro, Socratic tutor tab; static files served no-cache; sticky works (overflow-x clip); SPEC-008 (by `@claude-code`)

### Changed
- style: wrap a long usage guide line (by `@claude-code`)
- style: wrap the memory-strength usage line (by `@claude-code`)

### Fixed
- fix(web): resolve mobile simulator viewport mismatch when toggling iPhone 416px on desktop displays (ISSUE-026) (by `@antigravity`)
- fix(runner,quiz,sync): resolve quiz variant overwrite, forward custom prompts, fix artifact downloads, and fix SQLite multi-thread session handling (TASK-007) (by `@antigravity`)
- fix(web): switch default HTTP port from 8767 to 8768 to prevent collision with literature-parser (by `@antigravity`)
- fix(web): wire up background worker pool, auto-setup NotebookLM and add queue controls (by `@antigravity`)
- fix: resolve audit report issues across quiz variants, prompts, remote sync, study portal, and mcp tools (by `@antigravity`)
- fix(api,quiz): share database engine between services, sanitize json script tags, and document spec 004 (by `@antigravity`)
- fix(services): mark incomplete quizzes as needs_review and wire Ollama client into prompt refinement (by `@claude-code`)
- fix(notebooklm): pass zh_Hant language, wait for and target generated artifact ids, detect quota status, and switch Ollama to gemma4 (by `@claude-code`)
- fix(db): keep NotebookLM source ids of unchanged PDFs when re-registering a course (by `@claude-code`)
- fix(audio): save NotebookLM audio as .m4a and serve it as audio/mp4 (by `@claude-code`)
- fix(queue): pre-check live quota, estimate workloads from real costs, quarantine short mock exams, serve needs_review files, and correct docs (by `@claude-code`)
- fix(env): resolve PIL to Pillow import hint mapping in setup_env and standardize pyproject dependency case (by `@antigravity`)
- fix: short videos use auto style, and regenerating uses the current prompt blueprint instead of a stale stored prompt (by `@claude-code`)
- fix(web): style number and text inputs in the settings panels (by `@claude-code`)
- fix: shuffle quiz options (answers were 72% A), course card fields, study flashcards lookup, paused status message (by `@claude-code`)
- fix: request-scoped DB sessions (connection pool exhaustion caused Failed to fetch); save and reuse NotebookLM explanations; render their Markdown; no horizontal scrolling at any width (by `@claude-code`)
- fix(web): every button works - add job prompt view/edit routes (HTTP+MCP), wake-quota button uses /api/queue/resume, downloads answer HEAD; dialogs close with X, outside click or Esc; header splits status from actions; title returns home; quiz choices reshuffle on every attempt; offline banner instead of Failed to fetch (by `@claude-code`)
- fix: port check uses SO_REUSEADDR like uvicorn so a just-stopped server's TIME_WAIT port does not block the launcher (by `@claude-code`)
- fix(learning): live test fixes - quote matching ignores punctuation and empty text pieces (12/12 Gemini Notebook key points found), points fade only after their pages are drawn, citation markers stripped from tutor replies and explanations (by `@claude-code`)
- fix(test): set SO_REUSEADDR on test server socket for Linux TIME_WAIT reuse (ISSUE-025) (by `@antigravity`)

### Documentation
- docs: synchronize ARCHITECTURE.md, DB.md, README.md, and PROJECT_RULES with SPEC-006~008 and new DB models (by `@antigravity`)
- docs(adr): add ADR-002 (session token authentication) and ADR-003 (student study portal and spaced repetition) (by `@antigravity`)
- docs(specs): add specs 001-004 and ADR-001 for NotebookLM batch generation (by `@claude-code`)
- docs(adr): document empirical verification results for NotebookLM single-source selection and artifact downloads (TASK-001) (`TASK-001`, by `@antigravity`)
- docs(adr): add ADR-004 (artifact ID targeting) and ADR-005 (job versions and generation options) (by `@claude-code`)
- docs(specs): add SPEC-005 for generation options, versioned regeneration, and naming guide (by `@claude-code`)
- docs: update README, ARCHITECTURE, PROJECT_RULES, and SPECS for Study Portal, versioned regeneration, and device-sized infographics (TASK-010) (by `@antigravity`)
- docs: synchronize all documentation, architecture, specs, and records (by `@antigravity`)
- docs(docs): update docs documentation (ADR-001, ADR-002, ADR-003, ADR-005, ADR-006, ISSUE-001, ISSUE-016, ISSUE-021, ISSUE-024, TASK-001, TASK-003, TASK-004, TASK-005) (by `@antigravity`)
- docs(standards): sync web app and architecture rules from template (by `@antigravity`)
- docs(adr/docs): update adr/docs documentation (ADR-004, ADR-005, ADR-006, ADR-007, ISSUE-022, ISSUE-023, ISSUE-024, ISSUE-025, ISSUE-026, TASK-001, TASK-005, TASK-007, TASK-009) (by `@antigravity`)

### Chore
- chore: remove template greeting code and table, and the dummy sample PDF generator (by `@claude-code`)
- chore(deps): upgrade notebooklm-py to 0.8.6; docs: per-artifact settings design, known issues 016-017, README web features (by `@claude-code`)
- chore(framework): sync framework updates and add project-auditor skill (by `@antigravity`)

## [0.1.0] - 2026-10-21
### Added
- Initial project scaffold (framework v3.3.0).
