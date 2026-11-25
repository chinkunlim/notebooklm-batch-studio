# 專案完整檔案與資料夾結構樹 (PROJECT_TREE)

> ⚠️ 本檔案由 `python3 scripts/agentctl.py tree` 自動產生，請勿手動編輯。

```text
notebooklm-batch-studio/
├── .agents/                                # 【AI Agent 框架層】專案設定、共用函式庫、Skills、任務卡與交接紀錄
│   ├── bin/                                # [框架腳本] commit、任務、收尾、doctor、update…（由 agentctl 呼叫）
│   │   ├── agent_task.py
│   │   ├── agentctl.py
│   │   ├── audit_trail.py
│   │   ├── auto_commit.py
│   │   ├── build_graph.py
│   │   ├── check_staged.py
│   │   ├── conversations.py
│   │   ├── doctor.py
│   │   ├── finish.py
│   │   ├── setup_env.py
│   │   ├── sync_agent_adapters.py
│   │   ├── update_framework.py
│   │   └── update_tree.py
│   ├── handoff/                            # [交接紀錄] 頂部即時狀態看板 + 歷史交接時間軸，開工前必讀
│   │   ├── ARCHIVE.md                      # [歷史交接歸檔] 超過 20 筆之舊交接紀錄自動歸檔
│   │   └── LATEST.md                       # [即時交接看板] 目前分支、進行中/待接手任務、已完成與待辦事項
│   ├── hooks/                              # [版本控管的 git hooks] 由 core.hooksPath 啟用（pre-commit、pre-push）
│   │   ├── graphify-refresh.sh
│   │   ├── post-checkout
│   │   ├── post-commit
│   │   ├── post-merge
│   │   ├── pre-commit
│   │   └── pre-push
│   ├── lib/                                # 框架共用 Python 函式庫 (設定載入、目錄樹註解)
│   │   ├── framework_install.py
│   │   ├── project_config.py
│   │   └── tree_annotations.py
│   ├── skills/                             # 按任務觸發的模組化 Agent Skills (SKILL.md + scripts/*.py)
│   │   ├── adr-issue-tracker/              # [Skill] ADR 與 Known Issues 自動編號與索引
│   │   │   ├── scripts/
│   │   │   │   └── tracker_cli.py
│   │   │   └── SKILL.md
│   │   ├── api-adapter-scaffold/           # [Skill] 外部 API 防腐層產生器
│   │   │   ├── scripts/
│   │   │   │   └── scaffold_adapter.py
│   │   │   └── SKILL.md
│   │   ├── code-review-guard/              # [Skill] 註解、分層、秘密與函式大小靜態審查
│   │   │   ├── scripts/
│   │   │   │   └── review_guard.py
│   │   │   └── SKILL.md
│   │   ├── compliance-scanner/
│   │   │   ├── scripts/
│   │   │   │   └── scan_compliance.py
│   │   │   └── SKILL.md
│   │   ├── design-psychology-master/
│   │   │   ├── scripts/
│   │   │   │   └── design_audit.py
│   │   │   └── SKILL.md
│   │   ├── project-auditor/
│   │   │   ├── scripts/
│   │   │   │   └── audit_project_integrity.py
│   │   │   └── SKILL.md
│   │   ├── session-closeout/               # [Skill] 收尾：測試、對話紀錄（逐字稿＋摘要）、交接、Commit
│   │   │   ├── scripts/
│   │   │   │   └── closeout_runner.py
│   │   │   └── SKILL.md
│   │   ├── tdd-bugfix/                     # [Skill] 測試驅動開發與離線 Fixture 產生
│   │   │   ├── scripts/
│   │   │   │   └── tdd_runner.py
│   │   │   └── SKILL.md
│   │   └── catalog.json                    # [Skills 目錄] 各 skill 的分層 (core/stack/optional)、觸發時機與指令
│   ├── tasks/                              # [任務卡] 建立、接手、交接、完成 (agentctl task)
│   │   ├── TASK-001-phase-1a-notebooklm-technical-sp.json
│   │   ├── TASK-002-phase-1b-domain-parallel-queue.json
│   │   ├── TASK-003-phase-1c-notebooklm-adapter-conv.json
│   │   ├── TASK-004-phase-1d-cli-batch-orchestrator-.json
│   │   ├── TASK-005-phase-1e-openapi-mcp-web-ui-fast.json
│   │   ├── TASK-006-update-all-documentation-and-arc.json
│   │   ├── TASK-007-fix-ollama-prompt-refinement-and.json
│   │   ├── TASK-008-fix-notebooklm-language-artifact.json
│   │   ├── TASK-009-mind-map-rename-versioned-regene.json
│   │   ├── TASK-010-update-all-markdown-records-acro.json
│   │   ├── TASK-011-apply-v05-design-to-the-web-ui.json
│   │   ├── TASK-012-course-filter-in-all-in-progress.json
│   │   ├── TASK-013-apply-one-course-s-settings-to-o.json
│   │   ├── TASK-014-fix-incomplete-course-deletion-c.json
│   │   ├── TASK-015-fix-workerpool-blocked-quota-typ.json
│   │   ├── TASK-016-fix-course-overall-output-progre.json
│   │   ├── TASK-017-dummy-mode-end-to-end-chaos-fool.json
│   │   ├── TASK-018-analyze-graphify-report-and-proj.json
│   │   ├── TASK-019-audit-all-resolved-known-issues-.json
│   │   ├── TASK-020-fix-course-code-collision-overwr.json
│   │   ├── TASK-021-fix-failed-artifact-job-manual-r.json
│   │   ├── TASK-022-support-adding-missing-artifacts.json
│   │   ├── TASK-023-add-notebook-source-listing-uplo.json
│   │   ├── TASK-024-spec-011-gemini-notebook-explora.json
│   │   ├── TASK-025-integrate-literature-fetch-and-u.json
│   │   ├── TASK-026-integrate-note-studio-phase-1-mo.json
│   │   ├── TASK-027-integrate-note-studio-phase-2-st.json
│   │   ├── TASK-028-security-hardening-and-code-revi.json
│   │   ├── TASK-029-records-audit-port-source-projec.json
│   │   ├── TASK-030-close-security-hardening-http-40.json
│   │   ├── TASK-031-resolve-issue-053-port-gemini-we.json
│   │   ├── TASK-032-resolve-issue-054-close-stale-ru.json
│   │   ├── TASK-033-audit-records-unify-mcp-confirm-.json
│   │   ├── TASK-034-fix-issue-054-regression-guard-l.json
│   │   ├── TASK-035-study-library-course-identity-an.json
│   │   ├── TASK-036-checklist.md
│   │   ├── TASK-036-user-manual-verification-and-hou.json
│   │   ├── TASK-037-textbook-chapters-as-lecture-sou.json
│   │   ├── TASK-038-backlog-course-display-name-edit.json
│   │   ├── TASK-039-wire-study-library-registration-.json
│   │   ├── TASK-040-learning-site-artifacts-per-lect.json
│   │   ├── TASK-041-link-115-1-cp30210-to-its-existi.json
│   │   ├── TASK-042-investigate-blocked-playwright-s.json
│   │   └── TASK-043-deprecate-migrate-study-layout-i.json
│   ├── framework.lock                      # [框架鎖定檔] 框架版本與檔案雜湊，供 update_framework 判斷是否被修改
│   ├── mcp_config.json                     # [AI 工具] Antigravity 的專案 MCP 設定
│   └── project.toml                        # [專案設定・各專案自訂] 語言、分層、品質門檻、指令、業務規則
├── .cursor/                                # [Agent 轉接] Cursor 規則 (自動產生)
│   ├── rules/
│   │   └── 00-project-constitution.mdc
│   └── mcp.json
├── .github/                                # 【自動化護欄層】CI、PR 範本與 Copilot 入口
│   ├── workflows/                          # CI/CD 自動化檢查工作流程
│   │   └── ci.yml                          # 金鑰掃描、目錄樹檢查、程式審查與離線測試
│   └── copilot-instructions.md             # [Agent 轉接檔] GitHub Copilot 入口 (自動產生)
├── .vscode/
│   ├── extensions.json
│   ├── launch.json
│   ├── mcp.json
│   └── settings.json
├── .windsurf/                              # [Agent 轉接] Windsurf 規則 (自動產生)
│   └── rules/
│       └── 00-project-constitution.md
├── alembic/
│   ├── versions/
│   │   ├── 20260101_0001_create_greetings.py
│   │   ├── 20261022_0645db844501_add_source_id_to_lectures.py
│   │   ├── 20261022_7c7fdb56abf2_create_course_lecture_artifact_jobs_and_.py
│   │   ├── 20261101_17572899c2da_add_saved_explanations.py
│   │   ├── 20261101_3dbb5819dc15_add_style_options_interactive_path_and_.py
│   │   ├── 20261101_4985a300eaa2_add_quiz_attempts_and_mistakes.py
│   │   ├── 20261101_7b0938de08f1_drop_template_greetings_table.py
│   │   ├── 20261101_b3bed90c05da_add_key_points_tutor_messages_and_.py
│   │   ├── 20261101_b6ac72489fc1_add_study_progress_and_review_items.py
│   │   ├── 20261101_cff6ba027876_add_upload_status_and_custom_prompt.py
│   │   ├── 20261101_d0a82d2914ab_persist_course_artifact_selections.py
│   │   ├── 20261101_d21a28b5d5a0_add_course_paused_and_reuse_notebook_.py
│   │   ├── 20261101_d6e896ae4e2c_add_job_version_artifact_ids_and_course_.py
│   │   ├── 20261102_89158d42494d_add_ui_preferences.py
│   │   ├── 20261114_393ba6cc4afd_add_course_qa_notes_table.py
│   │   ├── 20261122_85aedf6f2f6f_add_review_markdown_to_literature_items.py
│   │   ├── 20261122_8f8dfcf0509e_add_study_hierarchy_and_literature_.py
│   │   └── 20261125_c4d5e6f7a8b9_course_status_and_course_no.py
│   ├── DB.md
│   ├── env.py
│   └── script.py.mako
├── assets/
│   └── prompts/
│       ├── modular_specs/
│       │   ├── 01_mindmap_spec.md
│       │   ├── 02_outline_spec.md
│       │   ├── 03_qec_spec.md
│       │   ├── 04_cornell_spec.md
│       │   ├── 05_matrix_spec.md
│       │   ├── 06_feynman_spec.md
│       │   ├── 07_quiz_spec.md
│       │   ├── 08_supplement_spec.md
│       │   └── MODULAR_SPECS.md
│       └── notebook_site/
│           └── learning_site.md
├── docs/                                   # 【工程知識庫】架構、規格、決策、已知問題、維運、規範
│   ├── adr/                                # [架構決策庫] 一決定一檔案
│   │   ├── 001-notebooklm-access.md
│   │   ├── 002-session-token-auth.md
│   │   ├── 003-student-study-portal-spaced-repetition.md
│   │   ├── 004-artifact-id-targeting.md
│   │   ├── 005-job-versions-and-generation-options.md
│   │   ├── 006-gemini-notebook-display-name.md
│   │   ├── 007-study-studio-visual-tiering-and-agency-architecture.md
│   │   ├── 008-v05-study-studio-shell.md
│   │   ├── 009-local-preferences-and-offline-fonts.md
│   │   ├── 010-notebook-qa-notes-and-tag-system.md
│   │   ├── 011-unified-study-hierarchy-and-literature-fetch.md
│   │   ├── 012-note-studio-phase1-markdown-pipeline.md
│   │   ├── 013-local-security-model.md
│   │   ├── 014-course-identity-and-study-layout.md
│   │   ├── 015-consolidation-exclusive-guard.md
│   │   ├── _TEMPLATE.md                    # ADR 範本 (tracker_cli 會套用)
│   │   └── DECISIONS.md                    # 架構決策總表
│   ├── architecture/                       # [系統架構與資料模型]
│   │   ├── ARCHITECTURE.md                 # 系統架構總覽 (手動) 與自動報告索引
│   │   ├── PROJECT_TREE.md                 # 完整檔案結構樹 (自動產生)
│   │   └── WORKFLOW_AND_COUPLING_ANALYSIS.md
│   ├── demo/
│   │   └── index.html
│   ├── design/
│   │   ├── DESIGN.md
│   │   ├── mockups_gallery.html
│   │   ├── version_01_classic_triptych.html
│   │   ├── version_02_dual_column_sanctuary.html
│   │   ├── version_03_luxury_turntable_visualizer.html
│   │   ├── version_04_workbench_customizer.html
│   │   └── version_05_claude_template.html
│   ├── known-issues/                       # [已知問題庫] 一問題一檔案
│   │   ├── 001-ollama-refine-noop.md
│   │   ├── 002-quiz-needs-review-status.md
│   │   ├── 003-nlm-output-language-english.md
│   │   ├── 004-artifact-wrong-lecture.md
│   │   ├── 005-quota-status-ignored.md
│   │   ├── 006-reregister-drops-source-ids.md
│   │   ├── 007-audio-m4a-named-mp3.md
│   │   ├── 008-quota-blind-scheduling.md
│   │   ├── 009-mock-exam-not-quarantined.md
│   │   ├── 010-needs-review-not-downloadable.md
│   │   ├── 011-mind-map-not-renamed.md
│   │   ├── 012-wrong-extensions-and-download-link.md
│   │   ├── 013-report-html-raw-text.md
│   │   ├── 014-artifact-selection-not-saved.md
│   │   ├── 015-cli-tests-use-real-db.md
│   │   ├── 016-report-instructions-ignored.md
│   │   ├── 017-quiz-prompts-ten-questions.md
│   │   ├── 018-study-portal-quiz-missing.md
│   │   ├── 019-start-checkbox-ignored.md
│   │   ├── 020-web-field-mismatch.md
│   │   ├── 021-answer-position-bias.md
│   │   ├── 022-quiz-submit-resets-view.md
│   │   ├── 023-db-connection-leak.md
│   │   ├── 024-buttons-calling-missing-routes.md
│   │   ├── 025-linux-time-wait-so-reuseaddr.md
│   │   ├── 026-mobile-simulator-viewport-media-query-mismatch.md
│   │   ├── 027-launcher-port-time-wait.md
│   │   ├── 028-stale-static-cache.md
│   │   ├── 029-sticky-broken-by-overflow-hidden.md
│   │   ├── 030-key-point-quote-matching.md
│   │   ├── 031-safari-sidebar-gap.md
│   │   ├── 032-page-switch-jank.md
│   │   ├── 033-stale-cache-overwrites-preferences.md
│   │   ├── 034-course-delete-incomplete-cleanup.md
│   │   ├── 035-worker-pool-blocked-quota-types-stuck.md
│   │   ├── 036-course-overall-progress-not-updating.md
│   │   ├── 037-course-code-collision-overwrites-notebook.md
│   │   ├── 038-failed-job-no-rerun-and-auto-retry.md
│   │   ├── 039-ui-focus-cram-reader-polish.md
│   │   ├── 040-ui-cram-reader-layout-controls.md
│   │   ├── 041-literature-playwright-request-blocked.md
│   │   ├── 042-literature-openalex-wrong-paper.md
│   │   ├── 043-literature-cloudflare-loop.md
│   │   ├── 044-literature-refresh-loses-or-downgrades-pdf.md
│   │   ├── 045-note-pipeline-path-traversal.md
│   │   ├── 046-prompt-injection-xss.md
│   │   ├── 047-literature-pdf-path-traversal.md
│   │   ├── 048-literature-mcp-missing-confirm.md
│   │   ├── 049-http-host-and-artifact-code.md
│   │   ├── 050-artifact-view-ignores-study-dir.md
│   │   ├── 051-reader-notes-premature-export.md
│   │   ├── 052-gemini-logger-legacy-name.md
│   │   ├── 053-gemini-web-login-entry-missing.md
│   │   ├── 054-literature-job-stays-running-after-crash.md
│   │   ├── 055-quiz-response-course-code-key.md
│   │   ├── 056-notes-form-lecture-fields.md
│   │   ├── 057-literature-stale-cleanup-kills-live-process-job.md
│   │   ├── 058-course-code-three-rule-inconsistency.md
│   │   ├── 059-watcher-only-monitors-input-courses.md
│   │   ├── 060-folder-picker-points-to-input-courses.md
│   │   ├── 061-reverse-import-uses-output-imported-sources.md
│   │   ├── 062-legacy-input-output-course-layout-writes.md
│   │   ├── 063-implicit-load-config-fallbacks.md
│   │   ├── 064-flashcards-cross-course-glob.md
│   │   ├── 065-delete-course-silently-drops-learning-records.md
│   │   ├── 066-auto-keypoints-422-before-upload.md
│   │   ├── 067-rename-course-misses-fallback-output-needs-review-and-active-locks.md
│   │   ├── 068-record-only-regenerate-without-notebook.md
│   │   ├── 069-migrate-moves-school-named-study-folders.md
│   │   ├── 070-notebooklm-py-rejects-html-download.md
│   │   ├── _TEMPLATE.md                    # 已知問題範本 (tracker_cli 會套用)
│   │   └── KNOWN_ISSUES.md                 # 已知問題總表 (🔴/🟡/🟢)
│   ├── specs/                              # [功能規格書] PRD / API Contract
│   │   ├── 001-batch-generation.md
│   │   ├── 002-export-downloads.md
│   │   ├── 003-web-and-ai-tools.md
│   │   ├── 004-phase2-self-test.md
│   │   ├── 005-generation-options-and-versions.md
│   │   ├── 006-per-artifact-settings.md
│   │   ├── 007-student-experience.md
│   │   ├── 008-learning-aids.md
│   │   ├── 009-study-studio-ui-redesign.md
│   │   ├── 010-user-end-to-end-workflow.md
│   │   ├── 011-notebook-qa-notes-and-tag-system.md
│   │   ├── 012-literature-fetch-and-study-hierarchy.md
│   │   ├── 013-note-studio-markdown-notes.md
│   │   ├── 014-study-library-and-learning-record.md
│   │   ├── 015-adopt-existing-outputs.md
│   │   ├── 016-study-library-web-management.md
│   │   ├── 017-notes-files-notifications-versions-backups.md
│   │   ├── 018-textbook-split-and-lecture-source.md
│   │   ├── 019-web-gap-fill-profile-resume-retention.md
│   │   ├── 020-textbook-detect-note-schedule-quota-resume.md
│   │   ├── 021-learning-site-artifacts.md
│   │   ├── _TEMPLATE.md                    # 規格範本
│   │   └── SPECS.md                        # 規格清單
│   ├── standards/                          # [工程規範] 依任務載入 (Progressive Disclosure)
│   │   ├── architecture/
│   │   │   ├── layers.md
│   │   │   └── workflow_parity.md
│   │   ├── coding/
│   │   │   ├── code_review_zero_tolerance.md
│   │   │   ├── comments.md
│   │   │   ├── data_guard.md
│   │   │   └── principles.md
│   │   ├── env/
│   │   │   ├── data_dir_layout.md
│   │   │   ├── icloud_rules.md
│   │   │   └── install_and_update.md
│   │   ├── testing/
│   │   │   ├── empirical_evidence.md
│   │   │   ├── sdd_bdd_tdd.md
│   │   │   └── virtual_testing.md
│   │   ├── web/
│   │   │   ├── fastapi_mcp.md
│   │   │   ├── modern_web_guidance.md
│   │   │   └── taste_design.md
│   │   ├── ARCHITECTURE_RULES.md           # 分層依賴與系統架構守則
│   │   ├── CODING_PRINCIPLES.md            # 註解規範、Karpathy 原則、SOLID、DRY、Atomic
│   │   ├── ENVIRONMENT_AND_DEPENDENCIES.md # uv / pnpm / Brewfile / 127.0.0.1 環境與依賴規範
│   │   ├── GIT_AND_VERSIONING.md           # Local Git、變更片段、發布與收尾規範
│   │   ├── LOCAL_AI_ENVIRONMENT.md
│   │   ├── MULTI_AGENT_COLLABORATION.md    # Agent 輪流接力：開工、交接、收尾與溯源
│   │   ├── PROJECT_RULES.md
│   │   ├── STANDARDS.md
│   │   └── TESTING_AND_QUALITY.md          # 測試金字塔與 DoD 驗收清單
│   ├── superpowers/
│   │   └── plans/
│   │       ├── 2026-11-14-notebook-qa-notes-and-tag-system.md
│   │       ├── 2026-11-24-study-library-and-learning-record.md
│   │       ├── 2026-11-25-learning-site-artifacts.md
│   │       └── 2026-11-25-next-session-master-plan.md
│   └── TEMPLATE_FEEDBACK.md
├── scripts/                                # 【專案腳本】agentctl.py 是框架的單一入口；其餘放本專案自己的腳本
│   ├── demo/
│   │   ├── demo-data.js
│   │   ├── demo-mock.js
│   │   └── demo-overrides.js
│   ├── agentctl.py                         # [單一入口] 轉呼叫 .agents/bin/agentctl.py
│   ├── build_demo.py
│   ├── build_mac_app.sh
│   ├── install.sh
│   ├── launch_app.sh
│   └── update.sh
├── src/                                    # 【核心原始碼層】分層與依賴方向定義於 .agents/project.toml
│   └── notebooklm_batch_studio/
│       ├── adapters/
│       │   ├── db/
│       │   │   ├── __init__.py
│       │   │   ├── base.py
│       │   │   ├── consolidation_repo.py
│       │   │   ├── course_identity_repo.py
│       │   │   ├── learning_repository.py
│       │   │   ├── literature_repository.py
│       │   │   ├── mappers.py
│       │   │   ├── models.py
│       │   │   ├── notes_repository.py
│       │   │   ├── preferences_repository.py
│       │   │   ├── queue_repository.py
│       │   │   ├── repository.py
│       │   │   ├── review_repository.py
│       │   │   ├── session.py
│       │   │   ├── study_migration_repo.py
│       │   │   └── study_repository.py
│       │   ├── fonts/
│       │   │   ├── __init__.py
│       │   │   └── google_fonts.py
│       │   ├── gemini/
│       │   │   ├── __init__.py
│       │   │   ├── auth_runtime.py
│       │   │   ├── browser_session.py
│       │   │   ├── chat_actions.py
│       │   │   ├── chrome_session.py
│       │   │   ├── model_controls.py
│       │   │   ├── response_reader.py
│       │   │   ├── selectors.py
│       │   │   └── web_driver.py
│       │   ├── literature/
│       │   │   ├── __init__.py
│       │   │   ├── airiti.py
│       │   │   ├── browser.py
│       │   │   ├── crossref.py
│       │   │   ├── ebsco.py
│       │   │   ├── factory.py
│       │   │   ├── files.py
│       │   │   ├── http_pdf.py
│       │   │   ├── legacy_import.py
│       │   │   ├── metadata.py
│       │   │   ├── openalex.py
│       │   │   ├── openlibrary.py
│       │   │   ├── pdf_text.py
│       │   │   ├── report_md.py
│       │   │   └── tracker_md.py
│       │   ├── notebooklm/
│       │   │   ├── __init__.py
│       │   │   ├── client.py
│       │   │   ├── client_artifacts.py
│       │   │   ├── client_remote_admin.py
│       │   │   ├── downloads.py
│       │   │   ├── errors.py
│       │   │   ├── generation.py
│       │   │   ├── note_driver.py
│       │   │   └── quota.py
│       │   ├── ollama/
│       │   │   ├── __init__.py
│       │   │   └── client.py
│       │   ├── __init__.py
│       │   ├── locks.py
│       │   ├── note_driver_factory.py
│       │   ├── pdf_textbook.py
│       │   ├── private_dir.py
│       │   ├── system_notify.py
│       │   └── web_search.py
│       ├── config/
│       │   ├── __init__.py
│       │   ├── data_paths.py
│       │   ├── logging_setup.py
│       │   ├── settings.py
│       │   └── study_layout.py
│       ├── domain/
│       │   ├── literature/
│       │   │   ├── __init__.py
│       │   │   ├── apa.py
│       │   │   ├── apa_format.py
│       │   │   ├── literature.py
│       │   │   └── tracker.py
│       │   ├── __init__.py
│       │   ├── course_identity.py
│       │   ├── exceptions.py
│       │   ├── generation_options.py
│       │   ├── memory_model.py
│       │   ├── models.py
│       │   ├── naming.py
│       │   ├── note_pipeline.py
│       │   ├── notebooklm_protocol.py
│       │   ├── path_safety.py
│       │   ├── qa_notes.py
│       │   ├── quota_parser.py
│       │   ├── repositories.py
│       │   ├── study_hierarchy.py
│       │   ├── study_layout.py
│       │   ├── study_plan.py
│       │   ├── textbook_sections.py
│       │   └── usage_guide.py
│       ├── entrypoints/
│       │   ├── http/
│       │   │   ├── __init__.py
│       │   │   ├── artifacts.py
│       │   │   ├── courses.py
│       │   │   ├── fonts.py
│       │   │   ├── gemini_auth.py
│       │   │   ├── learning.py
│       │   │   ├── literature.py
│       │   │   ├── literature_files.py
│       │   │   ├── literature_notebook.py
│       │   │   ├── note_schedule.py
│       │   │   ├── notes.py
│       │   │   ├── plan.py
│       │   │   ├── preferences.py
│       │   │   ├── qa_notes.py
│       │   │   ├── queue.py
│       │   │   ├── reverse_import.py
│       │   │   ├── settings.py
│       │   │   ├── study.py
│       │   │   ├── study_library.py
│       │   │   ├── system.py
│       │   │   └── textbooks.py
│       │   ├── static/
│       │   │   ├── vendor/
│       │   │   │   ├── fonts/
│       │   │   │   │   ├── noto-sans-tc/
│       │   │   │   │   │   ├── files/
│       │   │   │   │   │   │   ├── noto-sans-tc-0-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-1-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-10-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-101-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-102-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-103-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-104-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-105-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-106-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-107-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-108-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-109-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-11-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-110-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-111-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-112-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-113-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-114-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-115-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-116-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-117-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-118-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-119-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-12-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-120-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-121-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-122-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-123-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-2-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-23-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-24-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-25-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-26-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-27-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-28-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-29-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-30-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-31-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-32-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-33-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-34-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-35-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-36-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-37-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-38-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-39-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-4-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-40-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-41-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-42-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-43-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-44-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-45-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-46-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-47-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-48-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-49-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-50-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-51-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-52-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-53-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-54-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-55-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-56-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-57-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-58-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-59-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-60-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-61-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-62-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-63-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-64-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-65-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-66-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-67-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-68-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-69-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-70-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-71-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-72-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-73-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-74-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-75-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-76-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-77-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-78-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-79-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-80-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-81-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-82-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-83-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-84-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-85-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-86-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-87-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-88-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-89-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-90-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-91-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-92-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-93-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-94-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-95-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-96-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-cyrillic-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-latin-ext-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-sans-tc-latin-wght-normal.woff2
│       │   │   │   │   │   │   └── noto-sans-tc-vietnamese-wght-normal.woff2
│       │   │   │   │   │   ├── LICENSE
│       │   │   │   │   │   └── noto-sans-tc.css
│       │   │   │   │   ├── noto-serif-tc/
│       │   │   │   │   │   ├── files/
│       │   │   │   │   │   │   ├── noto-serif-tc-0-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-1-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-10-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-101-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-102-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-103-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-104-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-105-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-106-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-107-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-108-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-109-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-11-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-110-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-111-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-112-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-113-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-114-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-115-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-116-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-117-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-118-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-119-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-12-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-120-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-121-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-122-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-123-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-2-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-23-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-24-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-25-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-26-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-27-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-28-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-29-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-30-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-31-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-32-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-33-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-34-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-35-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-36-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-37-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-38-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-39-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-4-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-40-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-41-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-42-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-43-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-44-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-45-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-46-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-47-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-48-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-49-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-50-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-51-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-52-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-53-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-54-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-55-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-56-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-57-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-58-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-59-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-60-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-61-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-62-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-63-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-64-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-65-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-66-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-67-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-68-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-69-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-70-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-71-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-72-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-73-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-74-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-75-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-76-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-77-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-78-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-79-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-80-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-81-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-82-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-83-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-84-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-85-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-86-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-87-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-88-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-89-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-90-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-91-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-92-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-93-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-94-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-95-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-96-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-cyrillic-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-latin-ext-wght-normal.woff2
│       │   │   │   │   │   │   ├── noto-serif-tc-latin-wght-normal.woff2
│       │   │   │   │   │   │   └── noto-serif-tc-vietnamese-wght-normal.woff2
│       │   │   │   │   │   ├── LICENSE
│       │   │   │   │   │   └── noto-serif-tc.css
│       │   │   │   │   └── README.md
│       │   │   │   ├── lucide/
│       │   │   │   │   ├── LICENSE
│       │   │   │   │   ├── lucide.css
│       │   │   │   │   ├── lucide.woff2
│       │   │   │   │   └── README.md
│       │   │   │   └── pdfjs/
│       │   │   │       ├── LICENSE
│       │   │   │       ├── pdf.min.mjs
│       │   │   │       ├── pdf.worker.min.mjs
│       │   │   │       ├── README.md
│       │   │   │       └── text_layer.css
│       │   │   ├── icon-192.png
│       │   │   ├── icon-512.png
│       │   │   ├── index.html
│       │   │   ├── manifest.webmanifest
│       │   │   ├── studio-app.js
│       │   │   ├── studio-batch.js
│       │   │   ├── studio-bench.js
│       │   │   ├── studio-core.js
│       │   │   ├── studio-cram.js
│       │   │   ├── studio-escape.js
│       │   │   ├── studio-focus.js
│       │   │   ├── studio-fonts.js
│       │   │   ├── studio-habit-presets.js
│       │   │   ├── studio-hl-colors.js
│       │   │   ├── studio-layout-tune.js
│       │   │   ├── studio-learning.css
│       │   │   ├── studio-learning.js
│       │   │   ├── studio-library.js
│       │   │   ├── studio-literature-actions.js
│       │   │   ├── studio-literature-rows.js
│       │   │   ├── studio-literature-ui.js
│       │   │   ├── studio-literature.js
│       │   │   ├── studio-mindmap-designer.js
│       │   │   ├── studio-nav.js
│       │   │   ├── studio-note-schedule.js
│       │   │   ├── studio-notes-gen.js
│       │   │   ├── studio-notes-tab.js
│       │   │   ├── studio-pencil.js
│       │   │   ├── studio-pickers.js
│       │   │   ├── studio-player.js
│       │   │   ├── studio-qa-drawer.js
│       │   │   ├── studio-queue.js
│       │   │   ├── studio-reader-notes.js
│       │   │   ├── studio-reader.js
│       │   │   ├── studio-record.js
│       │   │   ├── studio-remote-artifacts.js
│       │   │   ├── studio-reverse-import.js
│       │   │   ├── studio-settings.js
│       │   │   ├── studio-shell.js
│       │   │   ├── studio-start.js
│       │   │   ├── studio-study-extras.js
│       │   │   ├── studio-study-panels.js
│       │   │   ├── studio-textbook.js
│       │   │   ├── studio-theme.css
│       │   │   ├── studio-wizard.js
│       │   │   ├── studio.css
│       │   │   └── studio.js
│       │   ├── __init__.py
│       │   ├── api.py
│       │   ├── cli.py
│       │   ├── cli_consolidate.py
│       │   ├── cli_literature.py
│       │   ├── http_middleware.py
│       │   ├── mcp_confirm.py
│       │   ├── mcp_course_settings.py
│       │   ├── mcp_extensions.py
│       │   ├── mcp_fonts.py
│       │   ├── mcp_gemini_auth.py
│       │   ├── mcp_job_prompts.py
│       │   ├── mcp_learning.py
│       │   ├── mcp_literature.py
│       │   ├── mcp_literature_notebook.py
│       │   ├── mcp_maintenance.py
│       │   ├── mcp_note_schedule.py
│       │   ├── mcp_notes.py
│       │   ├── mcp_preferences.py
│       │   ├── mcp_qa_notes.py
│       │   ├── mcp_remote_admin.py
│       │   ├── mcp_server.py
│       │   ├── mcp_studio_tools.py
│       │   ├── mcp_study_library.py
│       │   ├── mcp_study_plan.py
│       │   ├── mcp_textbooks.py
│       │   ├── note_runtime.py
│       │   ├── port_check.py
│       │   ├── schemas.py
│       │   └── web_template.py
│       ├── services/
│       │   ├── converters/
│       │   │   ├── __init__.py
│       │   │   ├── flashcard_converter.py
│       │   │   ├── image_fitter.py
│       │   │   ├── mindmap_converter.py
│       │   │   ├── mindmap_template.py
│       │   │   ├── note_pdf_renderer.py
│       │   │   ├── pdf_renderer.py
│       │   │   ├── quiz_converter.py
│       │   │   ├── quiz_formatter.py
│       │   │   └── report_converter.py
│       │   ├── literature/
│       │   │   ├── __init__.py
│       │   │   ├── archive.py
│       │   │   ├── export.py
│       │   │   ├── jobs.py
│       │   │   ├── literature.py
│       │   │   ├── manager.py
│       │   │   ├── manager_base.py
│       │   │   ├── notebook_service.py
│       │   │   ├── protocols.py
│       │   │   └── reference_builder.py
│       │   ├── notes/
│       │   │   ├── __init__.py
│       │   │   ├── chapter_normalizer.py
│       │   │   ├── gemini_auth_service.py
│       │   │   ├── module_composer.py
│       │   │   ├── module_prompts.py
│       │   │   ├── note_files.py
│       │   │   ├── note_paths.py
│       │   │   ├── note_pipeline_service.py
│       │   │   ├── note_scheduler.py
│       │   │   ├── note_sync.py
│       │   │   ├── state_manager.py
│       │   │   └── step_validator.py
│       │   ├── __init__.py
│       │   ├── adopt_outputs.py
│       │   ├── artifact_runner.py
│       │   ├── auth_status.py
│       │   ├── backups.py
│       │   ├── completion_notice.py
│       │   ├── course_display_name.py
│       │   ├── course_folders.py
│       │   ├── course_lifecycle.py
│       │   ├── course_onboarding.py
│       │   ├── course_options.py
│       │   ├── course_parser.py
│       │   ├── course_placement.py
│       │   ├── course_rename_files.py
│       │   ├── course_settings.py
│       │   ├── cram_service.py
│       │   ├── filing.py
│       │   ├── folder_browser.py
│       │   ├── font_service.py
│       │   ├── job_planner.py
│       │   ├── job_views.py
│       │   ├── learning_record.py
│       │   ├── learning_service.py
│       │   ├── legacy_consolidation.py
│       │   ├── legacy_consolidation_ops.py
│       │   ├── legacy_consolidation_planner.py
│       │   ├── orchestrator.py
│       │   ├── preferences_service.py
│       │   ├── prompt_generator.py
│       │   ├── qa_notes_formatter.py
│       │   ├── qa_notes_service.py
│       │   ├── quiz_reader.py
│       │   ├── quiz_runner.py
│       │   ├── quota_planner.py
│       │   ├── remote_admin_service.py
│       │   ├── reporter.py
│       │   ├── reverse_import.py
│       │   ├── source_manager.py
│       │   ├── study_library.py
│       │   ├── study_migration.py
│       │   ├── study_plan_service.py
│       │   ├── study_service.py
│       │   ├── sync_service.py
│       │   ├── textbook_split.py
│       │   ├── watcher.py
│       │   └── worker_pool.py
│       └── __init__.py
├── tests/                                  # 【測試層】單元與整合測試
│   ├── fixtures/
│   │   ├── notebooklm/
│   │   │   └── site_row.json
│   │   ├── apa_list.md
│   │   ├── crossref_search.json
│   │   ├── openalex_work.json
│   │   ├── sample_flashcards.json
│   │   ├── sample_mindmap.json
│   │   └── sample_quiz.json
│   ├── gemini/
│   │   ├── __init__.py
│   │   ├── test_browser_session.py
│   │   ├── test_chrome_session.py
│   │   ├── test_gemini_adapter.py
│   │   ├── test_gemini_auth.py
│   │   ├── test_gemini_copy_selector.py
│   │   ├── test_gemini_rename_logs.py
│   │   ├── test_gemini_response_count_baseline.py
│   │   ├── test_playwright_startup_timeout.py
│   │   └── test_quota_resume_parser.py
│   ├── literature/
│   │   ├── __init__.py
│   │   ├── test_airiti.py
│   │   ├── test_apa.py
│   │   ├── test_apa_format.py
│   │   ├── test_books.py
│   │   ├── test_chinese.py
│   │   ├── test_free_text.py
│   │   ├── test_literature.py
│   │   ├── test_literature_repository.py
│   │   ├── test_locks.py
│   │   ├── test_markdown_files.py
│   │   ├── test_stale_jobs.py
│   │   └── test_tracker.py
│   ├── __init__.py
│   ├── dummy_client.py
│   ├── test_adopt_outputs.py
│   ├── test_api_and_mcp.py
│   ├── test_auth_status.py
│   ├── test_auto_schedule.py
│   ├── test_button_routes.py
│   ├── test_converters.py
│   ├── test_course_admin.py
│   ├── test_course_identity.py
│   ├── test_course_lifecycle.py
│   ├── test_course_parser.py
│   ├── test_course_reregistration.py
│   ├── test_db.py
│   ├── test_domain_and_queue.py
│   ├── test_dummy_user_simulation.py
│   ├── test_failed_job_rerun.py
│   ├── test_filing.py
│   ├── test_fonts.py
│   ├── test_guides_and_reports.py
│   ├── test_install_scripts.py
│   ├── test_job_settings.py
│   ├── test_learning.py
│   ├── test_learning_record.py
│   ├── test_legacy_consolidation.py
│   ├── test_literature_and_hierarchy.py
│   ├── test_needs_review_and_ollama.py
│   ├── test_note_pipeline_behaviors.py
│   ├── test_note_pipeline_phase1.py
│   ├── test_note_pipeline_phase2.py
│   ├── test_notebooklm_adapter.py
│   ├── test_notebooklm_generation.py
│   ├── test_old_layout_retired.py
│   ├── test_path_pickers.py
│   ├── test_port_check.py
│   ├── test_preferences.py
│   ├── test_qa_notes_api.py
│   ├── test_qa_notes_db.py
│   ├── test_qa_notes_service.py
│   ├── test_quota_and_limits.py
│   ├── test_remaining_fixes.py
│   ├── test_remote_artifacts.py
│   ├── test_rename.py
│   ├── test_reverse_import.py
│   ├── test_security_hardening.py
│   ├── test_selection_and_folders.py
│   ├── test_services_and_cli.py
│   ├── test_settings_paths.py
│   ├── test_spec017_small_features.py
│   ├── test_study_layout.py
│   ├── test_study_library.py
│   ├── test_study_library_api.py
│   ├── test_study_library_web.py
│   ├── test_study_plan.py
│   ├── test_study_service.py
│   ├── test_textbook_split.py
│   ├── test_versions_and_options.py
│   └── test_web_gap_fill.py
├── .editorconfig
├── .env.example                            # [設定範本] 環境變數清單與預設值說明
├── .gitignore                              # [版控排除] 排除依賴、機密 .env、憑證與執行期快取
├── .graphifyignore
├── .mcp.json                               # [AI 工具] Claude Code 的專案 MCP 設定（uv run <名稱>-mcp）
├── .python-version                         # [Python 版本釘選] 供 uv / pyenv / mise 自動讀取
├── AGENTS.md                               # [AI 協作憲法・唯一規則來源] 所有 AI Agent 共用的開發原則與 Skills 路由
├── alembic.ini
├── CHANGELOG.md                            # [版本歷史] commit 寫入 Unreleased；agentctl finish --tag 發布版本
├── CLAUDE.md                               # [Agent 轉接檔] Claude Code 入口，匯入 AGENTS.md (自動產生)
├── GEMINI.md                               # [Agent 轉接檔] Gemini CLI 入口，指向 AGENTS.md (自動產生)
├── opencode.json                           # [AI 工具] OpenCode 的專案設定（MCP）
├── pyproject.toml                          # [PEP 621 單一真相來源] Python 中繼資料、依賴分組、pytest 與 ruff 設定
└── README.md                               # [唯一 README] 專案入口、快速開始與文件索引
```
