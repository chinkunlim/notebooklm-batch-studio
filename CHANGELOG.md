# Changelog

All notable changes to **notebooklm-batch-studio** are documented here
(format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versions: [SemVer](https://semver.org/)).

## [Unreleased]

### Added
- feat(spike): scaffold notebooklm spike script, sample pdf generator, and standard DATA_DIR paths (TASK-001) (`TASK-001`, by `@antigravity`)
- feat(domain,queue): implement course domain models, sqlite queue repository, course parser, and parallel worker pool (TASK-002) (`TASK-002`, by `@antigravity`)
- feat(adapter,converters): implement notebooklm adapter and quiz, flashcard, and mindmap converters (TASK-003) (by `@antigravity`)

### Documentation
- docs(specs): add specs 001-004 and ADR-001 for NotebookLM batch generation (by `@claude-code`)
- docs(adr): document empirical verification results for NotebookLM single-source selection and artifact downloads (TASK-001) (`TASK-001`, by `@antigravity`)

## [0.1.0] - 2026-10-21
### Added
- Initial project scaffold (framework v3.3.0).
