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
│   │   └── TASK-011-apply-v05-design-to-the-web-ui.json
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
│   │   └── 20261101_d6e896ae4e2c_add_job_version_artifact_ids_and_course_.py
│   ├── DB.md
│   ├── env.py
│   └── script.py.mako
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
│   │   ├── _TEMPLATE.md                    # ADR 範本 (tracker_cli 會套用)
│   │   └── DECISIONS.md                    # 架構決策總表
│   ├── architecture/                       # [系統架構與資料模型]
│   │   ├── ARCHITECTURE.md                 # 系統架構總覽 (手動) 與自動報告索引
│   │   └── PROJECT_TREE.md                 # 完整檔案結構樹 (自動產生)
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
│   │   ├── _TEMPLATE.md                    # 規格範本
│   │   └── SPECS.md                        # 規格清單
│   ├── standards/                          # [工程規範] 依任務載入 (Progressive Disclosure)
│   │   ├── ARCHITECTURE_RULES.md           # 分層依賴與系統架構守則
│   │   ├── CODING_PRINCIPLES.md            # 註解規範、Karpathy 原則、SOLID、DRY、Atomic
│   │   ├── ENVIRONMENT_AND_DEPENDENCIES.md # uv / pnpm / Brewfile / 127.0.0.1 環境與依賴規範
│   │   ├── GIT_AND_VERSIONING.md           # Local Git、變更片段、發布與收尾規範
│   │   ├── LOCAL_AI_ENVIRONMENT.md
│   │   ├── MULTI_AGENT_COLLABORATION.md    # Agent 輪流接力：開工、交接、收尾與溯源
│   │   ├── PROJECT_RULES.md
│   │   └── TESTING_AND_QUALITY.md          # 測試金字塔與 DoD 驗收清單
│   └── TEMPLATE_FEEDBACK.md
├── scripts/                                # 【專案腳本】agentctl.py 是框架的單一入口；其餘放本專案自己的腳本
│   ├── agentctl.py                         # [單一入口] 轉呼叫 .agents/bin/agentctl.py
│   ├── build_mac_app.sh
│   └── launch_app.sh
├── src/                                    # 【核心原始碼層】分層與依賴方向定義於 .agents/project.toml
│   └── notebooklm_batch_studio/
│       ├── adapters/
│       │   ├── db/
│       │   │   ├── __init__.py
│       │   │   ├── base.py
│       │   │   ├── learning_repository.py
│       │   │   ├── mappers.py
│       │   │   ├── models.py
│       │   │   ├── repository.py
│       │   │   ├── review_repository.py
│       │   │   ├── session.py
│       │   │   └── study_repository.py
│       │   ├── notebooklm/
│       │   │   ├── __init__.py
│       │   │   ├── client.py
│       │   │   ├── downloads.py
│       │   │   ├── generation.py
│       │   │   └── quota.py
│       │   ├── ollama/
│       │   │   ├── __init__.py
│       │   │   └── client.py
│       │   └── __init__.py
│       ├── config/
│       │   ├── __init__.py
│       │   ├── logging_setup.py
│       │   └── settings.py
│       ├── domain/
│       │   ├── __init__.py
│       │   ├── exceptions.py
│       │   ├── memory_model.py
│       │   ├── models.py
│       │   ├── naming.py
│       │   ├── notebooklm_protocol.py
│       │   ├── repositories.py
│       │   ├── study_plan.py
│       │   └── usage_guide.py
│       ├── entrypoints/
│       │   ├── http/
│       │   │   ├── __init__.py
│       │   │   ├── artifacts.py
│       │   │   ├── courses.py
│       │   │   ├── learning.py
│       │   │   ├── plan.py
│       │   │   ├── queue.py
│       │   │   ├── settings.py
│       │   │   ├── study.py
│       │   │   └── system.py
│       │   ├── static/
│       │   │   ├── vendor/
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
│       │   │   ├── studio-learning.css
│       │   │   ├── studio-learning.js
│       │   │   ├── studio-player.js
│       │   │   ├── studio-reader.js
│       │   │   ├── studio-settings.js
│       │   │   ├── studio-shell.js
│       │   │   ├── studio-start.js
│       │   │   ├── studio-theme.css
│       │   │   ├── studio.css
│       │   │   └── studio.js
│       │   ├── __init__.py
│       │   ├── api.py
│       │   ├── cli.py
│       │   ├── mcp_course_settings.py
│       │   ├── mcp_job_prompts.py
│       │   ├── mcp_learning.py
│       │   ├── mcp_server.py
│       │   ├── mcp_study_plan.py
│       │   ├── port_check.py
│       │   ├── schemas.py
│       │   └── web_template.py
│       ├── services/
│       │   ├── converters/
│       │   │   ├── __init__.py
│       │   │   ├── flashcard_converter.py
│       │   │   ├── image_fitter.py
│       │   │   ├── mindmap_converter.py
│       │   │   ├── pdf_renderer.py
│       │   │   ├── quiz_converter.py
│       │   │   └── report_converter.py
│       │   ├── __init__.py
│       │   ├── artifact_runner.py
│       │   ├── course_parser.py
│       │   ├── course_settings.py
│       │   ├── folder_browser.py
│       │   ├── job_views.py
│       │   ├── learning_service.py
│       │   ├── orchestrator.py
│       │   ├── prompt_generator.py
│       │   ├── quiz_reader.py
│       │   ├── quota_planner.py
│       │   ├── reporter.py
│       │   ├── study_plan_service.py
│       │   ├── study_service.py
│       │   ├── sync_service.py
│       │   ├── watcher.py
│       │   └── worker_pool.py
│       └── __init__.py
├── tests/                                  # 【測試層】單元與整合測試
│   ├── fixtures/
│   │   ├── sample_flashcards.json
│   │   ├── sample_mindmap.json
│   │   └── sample_quiz.json
│   ├── __init__.py
│   ├── test_api_and_mcp.py
│   ├── test_button_routes.py
│   ├── test_converters.py
│   ├── test_course_admin.py
│   ├── test_course_parser.py
│   ├── test_course_reregistration.py
│   ├── test_db.py
│   ├── test_domain_and_queue.py
│   ├── test_guides_and_reports.py
│   ├── test_job_settings.py
│   ├── test_learning.py
│   ├── test_needs_review_and_ollama.py
│   ├── test_notebooklm_adapter.py
│   ├── test_notebooklm_generation.py
│   ├── test_port_check.py
│   ├── test_quota_and_limits.py
│   ├── test_remaining_fixes.py
│   ├── test_rename.py
│   ├── test_selection_and_folders.py
│   ├── test_services_and_cli.py
│   ├── test_study_plan.py
│   ├── test_study_service.py
│   └── test_versions_and_options.py
├── .editorconfig
├── .env.example                            # [設定範本] 環境變數清單與預設值說明
├── .gitignore                              # [版控排除] 排除依賴、機密 .env、憑證與執行期快取
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
