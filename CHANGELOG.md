# Changelog

All notable changes to **notebooklm-batch-studio** are documented here
(format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versions: [SemVer](https://semver.org/)).

## [Unreleased]

### Added
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

### Fixed
- fix(runner,quiz,sync): resolve quiz variant overwrite, forward custom prompts, fix artifact downloads, and fix SQLite multi-thread session handling (TASK-007) (by `@antigravity`)
- fix(web): switch default HTTP port from 8767 to 8768 to prevent collision with literature-parser (by `@antigravity`)
- fix(web): wire up background worker pool, auto-setup NotebookLM and add queue controls (by `@antigravity`)
- fix: resolve audit report issues across quiz variants, prompts, remote sync, study portal, and mcp tools (by `@antigravity`)
- fix(api,quiz): share database engine between services, sanitize json script tags, and document spec 004 (by `@antigravity`)
- fix(services): mark incomplete quizzes as needs_review and wire Ollama client into prompt refinement (by `@claude-code`)
- fix(notebooklm): pass zh_Hant language, wait for and target generated artifact ids, detect quota status, and switch Ollama to gemma4 (by `@claude-code`)
- fix(db): keep NotebookLM source ids of unchanged PDFs when re-registering a course (by `@claude-code`)

### Documentation
- docs(adr): add ADR-002 (session token authentication) and ADR-003 (student study portal and spaced repetition) (by `@antigravity`)
- docs(specs): add specs 001-004 and ADR-001 for NotebookLM batch generation (by `@claude-code`)
- docs(adr): document empirical verification results for NotebookLM single-source selection and artifact downloads (TASK-001) (`TASK-001`, by `@antigravity`)
- docs: update README, ARCHITECTURE, and SPECS to reflect Phase 1 implementation (TASK-006) (by `@antigravity`)

## [0.1.0] - 2026-10-21
### Added
- Initial project scaffold (framework v3.3.0).
