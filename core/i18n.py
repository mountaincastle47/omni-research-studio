"""
OmniResearch Studio - Internationalization (i18n) Registry
Authoritative localized strings for English and natural Korean.
"""

from typing import Dict, Any

STRINGS: Dict[str, Dict[str, str]] = {
    # Window & Global Headers
    "app_title": {
        "en": "OmniResearch Studio — OmniSweep Discovery & Grounded Synthesis Workstation",
        "ko": "OmniResearch Studio — 다각도 웹 탐색 및 출처 기반 종합 분석 워크스테이션",
    },
    "app_subtitle": {
        "en": "Multi-Perspective OmniSweep Web Grounding • Zero-Temperature Citation Synthesis • Two-Host Audio Studio",
        "ko": "다각도 웹 탐색 • 출처 기반 무작위성 제로(0.0) 정밀 종합 • 2인 대화형 오디오 스튜디오",
    },
    "label_discovery_model": {
        "en": "Discovery Model:",
        "ko": "탐색 모델:",
    },
    "label_synthesis_model": {
        "en": "Synthesis Model:",
        "ko": "종합 모델:",
    },
    "label_language": {
        "en": "Language:",
        "ko": "언어:",
    },
    "api_key_active": {
        "en": "Active Key",
        "ko": "활성 API 키",
    },
    "api_key_none": {
        "en": "No Key Configured",
        "ko": "키가 설정되지 않음",
    },
    "btn_change_key": {
        "en": "Change",
        "ko": "변경",
    },
    "btn_apply_key": {
        "en": "Apply API Key",
        "ko": "키 적용",
    },
    "btn_clear_key": {
        "en": "Clear Stored Key",
        "ko": "저장된 키 삭제",
    },

    # Section 1: Reference Documents
    "sec1_title": {
        "en": "1. Reference Documents & Sources",
        "ko": "1. 참조 문서 및 소스 관리",
    },
    "btn_add_files": {
        "en": "+ Add Files (.pdf, .txt, .md)",
        "ko": "+ 파일 추가 (.pdf, .txt, .md)",
    },
    "btn_clear_all": {
        "en": "Clear All",
        "ko": "전체 삭제",
    },
    "btn_enable_all": {
        "en": "Enable All",
        "ko": "전체 선택",
    },
    "btn_disable_all": {
        "en": "Disable All",
        "ko": "전체 해제",
    },
    "btn_remove_selected": {
        "en": "Remove Selected",
        "ko": "선택 삭제",
    },
    "sources_count_label": {
        "en": "{active}/{total} active sources ({words} active words)",
        "ko": "선택된 자료 {active}/{total}개 (총 {words} 단어)",
    },

    # Section 2: OmniSweep Discovery
    "sec2_title": {
        "en": "2. OmniSweep Multi-Perspective Discovery",
        "ko": "2. OmniSweep 다각도 웹 탐색",
    },
    "label_select_personas": {
        "en": "Select Active Expert Perspectives:",
        "ko": "전문가 분석 관점 선택:",
    },
    "persona_technical": {
        "en": "Systems & Technical Architect",
        "ko": "시스템 및 기술 아키텍트",
    },
    "persona_skeptic": {
        "en": "Empirical & Methodological Skeptic",
        "ko": "실증 및 방법론적 검증",
    },
    "persona_economic": {
        "en": "Applied Domain & Economic Strategist",
        "ko": "실무 적용 및 경제성 분석",
    },
    "persona_historical": {
        "en": "Historical & Comparative Analyst",
        "ko": "역사 및 비교 분석",
    },
    "label_discovery_prompt": {
        "en": "Research Topic / Discovery Prompt:",
        "ko": "탐색 주제 및 연구 질문:",
    },
    "placeholder_discovery_prompt": {
        "en": "Enter research topic, target technologies, historical context, or specific questions...",
        "ko": "조사할 연구 주제, 핵심 기술, 역사적 배경 또는 구체적인 질문을 입력하세요...",
    },
    "btn_run_discovery": {
        "en": "Run OmniSweep Web Discovery (Google Search)",
        "ko": "다각도 웹 탐색 시작 (Google 검색)",
    },

    # Section 3: Grounded Synthesis
    "sec3_title": {
        "en": "3. Grounded Synthesis & Query (Zero-Temperature)",
        "ko": "3. 출처 기반 심층 분석 및 보고서 작성 (무작위성 0.0)",
    },
    "placeholder_synthesis_query": {
        "en": "Enter your research question or synthesis directive...\nEvery claim in the output will be strictly grounded in enabled sources with [N] citations.",
        "ko": "분석할 연구 질문이나 보고서 작성 지침을 입력하세요...\n모든 서술은 선택된 참조 자료만을 바탕으로 작성되며, 본문에 [N] 출처 번호가 표기됩니다.",
    },
    "btn_synthesize": {
        "en": "Synthesize Grounded Report (Temp = 0.0)",
        "ko": "출처 기반 종합 보고서 작성 (Temp = 0.0)",
    },
    "btn_export_markdown": {
        "en": "Save Report (.md)",
        "ko": "보고서 파일 저장 (.md)",
    },

    # Workspace Tabs & Viewer
    "workspace_group_title": {
        "en": "Synthesis & Multi-Perspective Workspace",
        "ko": "보고서 및 다각도 분석 워크스페이스",
    },
    "tab_synthesis_report": {
        "en": "Grounded Synthesis Report",
        "ko": "출처 기반 종합 보고서",
    },
    "tab_perspective_reports": {
        "en": "OmniSweep Perspective Reports",
        "ko": "관점별 탐색 리포트",
    },
    "btn_show_translation": {
        "en": "Show Translation",
        "ko": "번역문 보기",
    },
    "btn_show_original": {
        "en": "Show Original",
        "ko": "원문 보기",
    },
    "status_translating": {
        "en": "Translating to Korean in background...",
        "ko": "백그라운드에서 한국어로 번역 중...",
    },

    # Section 4: Right Inspector (Citations & Audio)
    "tab_citations": {
        "en": "Grounding Citations",
        "ko": "근거 출처",
    },
    "tab_audio_studio": {
        "en": "Audio Briefing Studio",
        "ko": "오디오 브리핑 스튜디오",
    },
    "header_citations_inspector": {
        "en": "Verified Synthesis Citations",
        "ko": "본문 인용 출처",
    },
    "no_citations_yet": {
        "en": "No bracketed citations extracted yet.",
        "ko": "본문에서 추출된 출처 표기가 아직 없습니다.",
    },
    "header_web_uris": {
        "en": "Google Search Grounding Sources",
        "ko": "Google 검색 출처 링크",
    },
    "web_uris_help": {
        "en": "Run OmniSweep Web Discovery to populate verified Google Search sources.",
        "ko": "다각도 웹 탐색을 실행하면 수집된 Google 검색 출처가 여기에 표시됩니다.",
    },
    "audio_studio_desc": {
        "en": "Transform your synthesis and active sources into a two-host conversational audio briefing script.",
        "ko": "작성된 종합 보고서와 수집 자료를 2인 대화형 팟캐스트 브리핑 대본으로 변환합니다.",
    },
    "placeholder_audio_directive": {
        "en": "Optional focus directive (e.g., debate technical bottlenecks, evaluate opposing evidence, or explore design failures)...",
        "ko": "대화 중점 사항 (선택: 기술적 병목 분석, 쟁점 토론, 설계 결함 및 한계점 심층 탐구 등)...",
    },
    "btn_generate_audio": {
        "en": "Generate Two-Host Audio Script",
        "ko": "2인 대화 대본 생성",
    },
    "btn_export_audio": {
        "en": "Save Script (.txt)",
        "ko": "대본 파일 저장 (.txt)",
    },

    # Welcome Splash
    "welcome_title": {
        "en": "Welcome to OmniResearch Studio",
        "ko": "OmniResearch Studio 안내",
    },
    "welcome_step1": {
        "en": "1. Upload local documents (.pdf, .txt, .md) or run OmniSweep Web Discovery on the left.",
        "ko": "1. 좌측에서 참조 문서(.pdf, .txt, .md)를 추가하거나 다각도 웹 탐색을 실행하세요.",
    },
    "welcome_step2": {
        "en": "2. Enter your synthesis question above and click Synthesize Grounded Report.",
        "ko": "2. 상단에 분석 질문을 입력하고 출처 기반 종합 보고서 작성을 클릭하세요.",
    },
    "welcome_step3": {
        "en": "3. Inspect [N] citations on the right, or generate a Two-Host Audio Overview.",
        "ko": "3. 우측에서 본문 출처를 확인하거나 2인 대화형 오디오 대본을 생성하세요.",
    },

    # Cancellation, Caching & Progress Strip
    "btn_cancel": {
        "en": "Cancel Task",
        "ko": "작업 취소",
    },
    "btn_cancelling": {
        "en": "Cancelling...",
        "ko": "취소 중...",
    },
    "status_canceling": {
        "en": "Canceling active task...",
        "ko": "작업 취소 중...",
    },
    "status_cancelled": {
        "en": "Task aborted by user.",
        "ko": "사용자에 의해 작업이 취소되었습니다.",
    },
    "status_cache_hit": {
        "en": "Loaded from cache (0 tokens consumed).",
        "ko": "캐시된 결과 불러옴 (토큰 소모 없음).",
    },
    "eta_Prefix": {
        "en": "ETA: ~{seconds}s",
        "ko": "남은 시간: 약 {seconds}초",
    },
    "eta_ready": {
        "en": "ETA: 0s",
        "ko": "완료",
    },

    # Interactive Citations & Citation Audit
    "citation_audit_pass": {
        "en": "✓ Groundedness: {score}% ({valid}/{total} verified)",
        "ko": "✓ 근거 일치율: {score}% ({valid}/{total}개 출처 검증됨)",
    },
    "citation_audit_warn": {
        "en": "⚠ Groundedness: {score}% ({valid}/{total} verified, {invalid} unmatched)",
        "ko": "⚠ 근거 일치율: {score}% ({valid}/{total}개 출처 검증됨, {invalid}개 불일치)",
    },
    "citation_audit_none": {
        "en": "No citations to audit yet.",
        "ko": "검증할 출처 표기가 아직 없습니다.",
    },
    "status_citation_missing": {
        "en": "Citation [{n}] does not match any active source.",
        "ko": "출처 [{n}]번은 선택된 참조 자료와 일치하지 않습니다.",
    },
    "status_citation_focused": {
        "en": "Showing citation [{n}].",
        "ko": "출처 [{n}]번을 표시했습니다.",
    },

    # Source Document Inspector
    "source_inspector_title": {
        "en": "Source Document Inspector",
        "ko": "참조 문서 상세 검사기",
    },
    "inspector_label_title": {"en": "Title", "ko": "제목"},
    "inspector_label_origin": {"en": "Origin Type", "ko": "자료 유형"},
    "inspector_label_words": {"en": "Word Count", "ko": "단어 수"},
    "inspector_label_tokens": {"en": "Estimated Tokens", "ko": "예상 토큰 수"},
    "inspector_label_location": {"en": "Location", "ko": "위치"},
    "inspector_btn_open_url": {"en": "Open Original Web Page", "ko": "원본 웹페이지 열기"},
    "inspector_search_placeholder": {"en": "Search keywords in this document...", "ko": "문서 내 키워드 검색..."},
    "inspector_btn_prev": {"en": "Prev", "ko": "이전"},
    "inspector_btn_next": {"en": "Next", "ko": "다음"},
    "inspector_empty_hint": {
        "en": "Double-click any document in Section 1 to inspect its source text and metadata.",
        "ko": "1번 참조 문서 목록에서 항목을 더블클릭하면 전문과 메타데이터를 확인할 수 있습니다.",
    },
    "inspector_matches": {"en": "{n} match(es)", "ko": "{n}건 일치"},
    "inspector_no_match": {"en": "No matches", "ko": "일치 항목 없음"},
    "btn_close": {"en": "Close", "ko": "닫기"},
    "source_type_local_pdf": {"en": "Local PDF", "ko": "로컬 PDF 문서"},
    "source_type_local_txt": {"en": "Local Text File", "ko": "로컬 텍스트 파일"},
    "source_type_local_md": {"en": "Local Markdown File", "ko": "로컬 마크다운 파일"},
    "source_type_web_sweep": {"en": "Web Sweep Source", "ko": "웹 탐색 수집 자료"},
    "source_type_web_full_text": {"en": "Web Full-Text Article", "ko": "웹 문서 전문"},
    "source_type_web_snippet": {"en": "Web Search Snippet", "ko": "웹 검색 요약문"},

    # Neural Audio Studio
    "btn_render_audio": {
        "en": "Render Audio (.mp3)",
        "ko": "오디오 음성 변환 (.mp3)",
    },
    "btn_save_audio": {
        "en": "Save Audio (.mp3)",
        "ko": "오디오 파일 저장 (.mp3)",
    },
    "audio_player_empty": {
        "en": "No audio has been rendered yet. Generate a script, then render the neural voices.",
        "ko": "아직 변환된 오디오가 없습니다. 대본을 생성하면 신경망 음성으로 변환됩니다.",
    },
    "status_audio_rendering": {
        "en": "Rendering neural voices (edge-tts): {done}/{total} turns",
        "ko": "신경망 음성 변환 중 (edge-tts): {done}/{total}개 발화",
    },
    "status_audio_ready": {
        "en": "Audio briefing is ready to play.",
        "ko": "오디오 브리핑이 재생 준비되었습니다.",
    },
    "status_audio_failed": {
        "en": "Audio rendering failed (the script is kept): {error}",
        "ko": "오디오 변환에 실패했습니다 (대본은 유지됨): {error}",
    },
    "audio_script_need_first": {
        "en": "Generate an audio script first, then render it to speech.",
        "ko": "먼저 대화 대본을 생성한 뒤 음성으로 변환하세요.",
    },
    "audio_save_dialog_title": {"en": "Save Audio Briefing (.mp3)", "ko": "오디오 브리핑 저장 (.mp3)"},

    # Follow-Up Q&A Console
    "chat_drawer_toggle": {
        "en": "Follow-Up Q&A Console",
        "ko": "후속 심층 질의 콘솔",
    },
    "chat_placeholder": {
        "en": "Ask a follow-up question grounded in this report...",
        "ko": "작성된 보고서와 근거 자료에 대해 추가 질문을 입력하세요...",
    },
    "chat_btn_send": {"en": "Send", "ko": "질문 전송"},
    "chat_btn_clear": {"en": "Clear Chat", "ko": "대화 초기화"},
    "chat_empty_hint": {
        "en": "Ask anything about the report. Answers cite the active sources as [N].",
        "ko": "보고서에 대해 무엇이든 질문하세요. 답변에는 선택된 자료의 출처 번호 [N]이 표기됩니다.",
    },
    "chat_role_user": {"en": "You", "ko": "나"},
    "chat_role_assistant": {"en": "OmniResearch Analyst", "ko": "OmniResearch 분석가"},
    "chat_need_material": {
        "en": "Run a Grounded Synthesis or add at least one enabled source before asking follow-up questions.",
        "ko": "후속 질의 전에 종합 보고서를 작성하거나 선택된 참조 자료를 1개 이상 준비하세요.",
    },
    "status_chat_answering": {
        "en": "Answering your follow-up question (gemini-3.8-flash)...",
        "ko": "후속 질문에 답변을 작성하는 중 (gemini-3.8-flash)...",
    },

    # Executive Exporter
    "btn_export_menu": {"en": "Export Report", "ko": "보고서 내보내기"},
    "export_as_md": {"en": "Save Markdown (.md)", "ko": "Markdown 저장 (.md)"},
    "export_as_html": {
        "en": "Save Interactive Report (.html)",
        "ko": "인터랙티브 웹 보고서 저장 (.html)",
    },
    "export_as_pdf": {
        "en": "Save Executive Report (.pdf)",
        "ko": "공식 보고서 저장 (.pdf)",
    },
    "status_export_saved": {"en": "Saved: {path}", "ko": "저장되었습니다: {path}"},
    "status_export_failed": {"en": "Export failed: {error}", "ko": "내보내기에 실패했습니다: {error}"},

    # Deep web ingestion & PDF OCR
    "status_scraping_web": {
        "en": "Deep-scraping full text from authoritative sources...",
        "ko": "핵심 출처 웹페이지 전문 스크래핑 중 (trafilatura)...",
    },
    "status_ocr_processing": {
        "en": "Running RapidOCR on scanned document pages...",
        "ko": "스캔 문서 페이지 RapidOCR 텍스트 인식 중...",
    },
    "contested_matrix_title": {
        "en": "Contested Claims & Empirical Anomalies",
        "ko": "상충 쟁점 및 실증 불일치 분석",
    },

    # Project persistence (.omni) & File menu
    "menu_file": {"en": "&File", "ko": "파일(&F)"},
    "menu_new_project": {"en": "New Project", "ko": "새 프로젝트"},
    "menu_open_project": {"en": "Open Project...", "ko": "프로젝트 열기..."},
    "menu_save_project": {"en": "Save Project", "ko": "프로젝트 저장"},
    "menu_save_as_project": {"en": "Save Project As...", "ko": "다른 이름으로 프로젝트 저장..."},
    "action_new_project": {"en": "New Project", "ko": "새 프로젝트"},
    "action_open_project": {"en": "Open Project (.omni)...", "ko": "프로젝트 열기 (.omni)..."},
    "action_save_project": {"en": "Save Project (.omni)", "ko": "프로젝트 저장 (.omni)"},
    "action_save_as_project": {"en": "Save Project As...", "ko": "다른 이름으로 프로젝트 저장..."},
    "project_untitled": {"en": "Untitled Project", "ko": "제목 없는 프로젝트"},
    "project_open_dialog": {"en": "Open Research Project", "ko": "연구 프로젝트 열기"},
    "project_save_dialog": {"en": "Save Research Project", "ko": "연구 프로젝트 저장"},
    "project_new_confirm_title": {"en": "Start a New Project?", "ko": "새 프로젝트를 시작할까요?"},
    "project_new_confirm_text": {
        "en": "The current workspace (sources, reports, audio, and chat) will be cleared. Unsaved work will be lost.",
        "ko": "현재 작업 공간(참조 자료, 보고서, 오디오, 대화 기록)이 초기화됩니다. 저장하지 않은 내용은 사라집니다.",
    },
    "project_error_title": {"en": "Project Error", "ko": "프로젝트 오류"},
    "status_project_saved": {
        "en": "Project saved successfully: {path}",
        "ko": "프로젝트가 성공적으로 저장되었습니다: {path}",
    },
    "status_project_loaded": {
        "en": "Project loaded successfully from {path}",
        "ko": "프로젝트를 성공적으로 불러왔습니다: {path}",
    },
    "status_project_new": {"en": "Started a new research project.", "ko": "새 연구 프로젝트를 시작했습니다."},

    # Telemetry, Autosave, & Workspace Tabs
    "telemetry_label": {
        "en": "Context: {tokens} / 1M ({pct}) | Spend: ~${cost}",
        "ko": "문맥 사용량: {tokens} / 1M ({pct}) | 예상 비용: ~${cost}",
    },
    "autosave_recovery_title": {
        "en": "Recover Previous Session",
        "ko": "이전 작업 세션 복구",
    },
    "autosave_recovery_msg": {
        "en": "An unsaved research session was detected from {time}. Would you like to restore it?",
        "ko": "{time}에 자동 저장된 연구 세션이 있습니다. 복구하시겠습니까?",
    },
    "tab_new": {
        "en": "New Research Workspace",
        "ko": "새 연구 워크스페이스",
    },
    "tab_rename_title": {
        "en": "Rename Workspace Tab",
        "ko": "연구 탭 이름 변경",
    },
    "tab_rename_prompt": {
        "en": "Enter new name for this research workspace:",
        "ko": "새 연구 워크스페이스의 이름을 입력하세요:",
    },
    "tab_close_confirm": {
        "en": "Are you sure you want to close this workspace tab?",
        "ko": "이 연구 탭을 닫으시겠습니까?",
    },

    # Phase 6: Production Hardening, FTS5 Search, Find Bar, Authority
    "action_search_fts": {
        "en": "Full-Text Search (FTS5)",
        "ko": "전문 검색 (FTS5)",
    },
    "search_fts_placeholder": {
        "en": "Search entire corpus (FTS5)... (Ctrl+Shift+F)",
        "ko": "전체 문서 및 보고서 통합 검색 (FTS5)... (Ctrl+Shift+F)",
    },
    "find_in_page_placeholder": {
        "en": "Find in report... (Ctrl+F)",
        "ko": "보고서 내 단어 찾기... (Ctrl+F)",
    },
    "find_in_report_placeholder": {
        "en": "Find in report... (Ctrl+F)",
        "ko": "보고서 내 단어 찾기... (Ctrl+F)",
    },
    "find_prev": {"en": "Previous", "ko": "이전"},
    "find_next": {"en": "Next", "ko": "다음"},
    "find_case_sensitive": {"en": "Match Case", "ko": "대소문자 구분"},
    "find_no_matches": {"en": "No matches", "ko": "일치 항목 없음"},
    "export_bibtex": {
        "en": "Export Citations (.bib)",
        "ko": "참고문헌 내보내기 (.bib)",
    },
    "drag_drop_overlay": {
        "en": "Drop files to add to corpus (.pdf, .docx, .txt, .omni)",
        "ko": "문서 파일을 놓아 참조 자료에 추가 (.pdf, .docx, .txt, .omni)",
    },
    "authority_primary": {
        "en": "Primary / Empirical",
        "ko": "1차 실증 자료",
    },
    "authority_secondary": {
        "en": "Secondary / Scholarly",
        "ko": "2차 학술/전문 자료",
    },
    "authority_tertiary": {
        "en": "Tertiary / Commentary",
        "ko": "3차 보도/해설 자료",
    },

    # Phase 7: Master Executive & Intelligence Suite
    "menu_view": {"en": "View", "ko": "보기"},
    "menu_split_view": {"en": "Split Comparison View", "ko": "분할 비교 뷰"},
    "menu_theme": {"en": "Theme", "ko": "테마"},
    "theme_dark": {"en": "Dark Studio", "ko": "다크 스튜디오"},
    "theme_oled": {"en": "OLED Black", "ko": "OLED 블랙"},
    "theme_light": {"en": "Academic Light", "ko": "학술용 라이트"},
    "export_obsidian": {"en": "Export to Obsidian (.md)", "ko": "Obsidian 마크다운 내보내기 (.md)"},
    "export_marp": {"en": "Export Presentation Deck (.marp.md)", "ko": "발표용 슬라이드 내보내기 (.marp.md)"},
    "network_offline_banner": {
        "en": "⚠ Offline Mode: Network disconnected. Local inspection and FTS5 search active.",
        "ko": "⚠ 오프라인 모드: 네트워크 연결 끊김. 로컬 문서 탐색 및 FTS5 검색만 지원됩니다.",
    },
    "redaction_notice": {
        "en": "Security: {count} sensitive tokens masked prior to API dispatch.",
        "ko": "보안 알림: API 전송 전 {count}개의 민감 정보가 자동 마스킹되었습니다.",
    },
    "sync_scroll": {"en": "Synchronized Scrolling", "ko": "동기화 스크롤"},
    "split_pane_select": {"en": "Compare with Tab:", "ko": "비교 대상 탭:"},
    "menu_typography": {"en": "Typography", "ko": "서체 및 글꼴"},
    "zoom_in": {"en": "Zoom In", "ko": "글꼴 확대"},
    "zoom_out": {"en": "Zoom Out", "ko": "글꼴 축소"},
    "zoom_reset": {"en": "Reset Zoom", "ko": "글꼴 크기 초기화"},
    "token_ledger_dialog_title": {"en": "API Token & Billing Ledger", "ko": "API 토큰 및 비용 원장"},
    "token_ledger_col_time": {"en": "Timestamp", "ko": "일시"},
    "token_ledger_col_model": {"en": "Model", "ko": "모델"},
    "token_ledger_col_prompt": {"en": "Prompt Tokens", "ko": "프롬프트 토큰"},
    "token_ledger_col_output": {"en": "Output Tokens", "ko": "출력 토큰"},
    "token_ledger_col_cached": {"en": "Cached Tokens", "ko": "캐시 토큰"},
    "token_ledger_col_cost": {"en": "Cost (USD)", "ko": "비용 (USD)"},

    # Phase 8: Cognitive Dominance & Deep Telemetry Suite
    "menu_checkpoints": {"en": "Manage Checkpoints...", "ko": "연구 분기 관리 (체크포인트)..."},
    "checkpoint_create": {"en": "Create Snapshot", "ko": "현재 상태 스냅샷 저장"},
    "checkpoint_restore": {"en": "Restore Snapshot", "ko": "선택한 분기로 복원"},
    "checkpoint_fork": {"en": "Fork Tab", "ko": "분기 복제"},
    "checkpoint_dialog_title": {"en": "Research Branching & Checkpoints", "ko": "연구 분기 관리 및 체크포인트"},
    "checkpoint_name_prompt": {"en": "Enter snapshot name:", "ko": "체크포인트 스냅샷 이름을 입력하세요:"},
    "local_llm_badge": {"en": "🔒 Air-Gapped Local Mode", "ko": "🔒 에어갭 로컬 모드"},
    "critic_verified": {"en": "Claim Entailment Verified", "ko": "실증적 진술 일치 검증 완료"},
    "critic_refuted": {"en": "Claim Not Supported by Cited Source", "ko": "인용 출처와 진술 불일치 감지"},
    "figures_panel_title": {"en": "Schematics & Figures", "ko": "추출된 도면 및 시각 자료"},
    "btn_zoom_figure": {"en": "Inspect Full Resolution", "ko": "고해상도 도면 확대"},
    "context_compression_label": {"en": "Smart Context Compression:", "ko": "스마트 컨텍스트 압축:"},
    "critic_badge_title": {"en": "Epistemic Critic", "ko": "비판적 사실 검증"},
    "critic_status_analyzing": {"en": "Evaluating borderline claim entailment...", "ko": "인용 진술 실증적 논리적 일치 여부 정밀 검증 중..."},

    # Phase 9: Deep Resilience & Intelligence Suite
    "menu_help": {"en": "&Help", "ko": "도움말(&H)"},
    "tab_causal_graph": {"en": "Causal Graph", "ko": "인과 다이어그램"},
    "tab_chronology": {"en": "Chronology", "ko": "연대표"},
    "menu_diagnostics": {"en": "System Health Check...", "ko": "시스템 진단 및 상태 점검..."},
    "diagnostic_title": {"en": "OmniResearch System Health Diagnostics", "ko": "OmniResearch 시스템 진단 및 상태 점검"},
    "diagnostic_run_btn": {"en": "Re-Run Health Check", "ko": "진단 다시 실행"},
    "status_transcribing_audio": {"en": "Transcribing audio/video media (faster-whisper)...", "ko": "오디오/비디오 미디어 음성 전사 중 (faster-whisper)..."},
    "status_resolving_academic": {"en": "Resolving academic paper and metadata via ArXiv/CrossRef...", "ko": "ArXiv/CrossRef 학술 논문 원문 및 메타데이터 자동 확인 중..."},
    "extraction_segfault_warning": {"en": "Extraction crashed isolated subprocess: file may be corrupted.", "ko": "문서 파싱 중 격리된 프로세스 오류 발생: 파일이 손상되었을 수 있습니다."},
    "chronology_filter_placeholder": {"en": "Filter events or dates...", "ko": "사건 또는 연도 필터링..."},
    "zoom_in_graph": {"en": "Zoom In", "ko": "그래프 확대"},
    "zoom_out_graph": {"en": "Zoom Out", "ko": "그래프 축소"},
    "reset_graph": {"en": "Reset Zoom", "ko": "배율 초기화"},

    # Phase 10: Master Production Hardening & Release Suite
    "btn_vision_analyze": {"en": "Analyze Figure with AI Vision", "ko": "AI 도면 정밀 분석"},
    "btn_diff_compare": {"en": "Compare Selected Documents (Diff)...", "ko": "선택 문서 버전 비교 (Diff)..."},
    "menu_diff_compare": {"en": "Compare Selected Documents (Diff)...", "ko": "선택 문서 버전 비교 (Diff)..."},
    "diff_dialog_title": {"en": "Visual Document Diff Inspector", "ko": "문서 텍스트 정밀 비교기"},
    "diff_doc_a_label": {"en": "Document A (Baseline):", "ko": "문서 A (기준):"},
    "diff_doc_b_label": {"en": "Document B (Comparison):", "ko": "문서 B (비교 대상):"},
    "diff_run_btn": {"en": "Run Text Diff Analysis", "ko": "텍스트 비교 실행"},
    "diff_metrics_label": {"en": "+{added} lines / -{deleted} lines / {unchanged} identical lines", "ko": "+{added}행 추가 / -{deleted}행 삭제 / {unchanged}행 일치"},
    "compute_cuda": {"en": "NVIDIA CUDA (FP16)", "ko": "NVIDIA CUDA 가속 (FP16)"} ,
    "compute_dml": {"en": "DirectML GPU (FP32)", "ko": "DirectML GPU 가속 (FP32)"},
    "compute_cpu": {"en": "CPU Multi-Core (INT8)", "ko": "CPU 다중 코어 (INT8)"},
    "epistemic_radar_title": {"en": "Epistemic Balance & Evidence Radar", "ko": "근거 신뢰도 및 출처 다각화 레이더"},
    "radar_axis_authority": {"en": "Authority Ratio", "ko": "1차 문헌 비율"},
    "radar_axis_linguistic": {"en": "Global Diversity", "ko": "다국어 다원성"},
    "radar_axis_dispersion": {"en": "Perspective Spread", "ko": "시각 분산도"},
    "crash_recovery_title": {"en": "Crash Recovery Sentinel", "ko": "비정상 종료 세션 복구 센티넬"},
    "crash_recovery_prompt": {"en": "A previous abnormal session crash was detected. Review the diagnostic trace below. Would you like to restore the previous project state?", "ko": "이전 세션의 비정상 종료 기록이 발견되었습니다. 아래 진단 로그를 확인하시고 이전 프로젝트 상태를 복원하시겠습니까?"},
    "crash_copy_trace_btn": {"en": "Copy Diagnostic Trace", "ko": "진단 로그 복사"},
    "crash_restore_btn": {"en": "Restore Session", "ko": "세션 복원"},
    "crash_dismiss_btn": {"en": "Dismiss", "ko": "무시"},
    "vision_status_analyzing": {"en": "Deconstructing schematic and transcribing embedded data curves with Gemini Vision...", "ko": "Gemini Vision으로 도면 분석 및 데이터 곡선/라벨 전사 중..."},
    "vision_note_title": {"en": "AI Vision Schematic Analysis", "ko": "AI 도면 정밀 분석"},

    # Phase 11: Autonomous Mastery & Sovereign Workflow Suite
    "tab_knowledge_graph": {"en": "Knowledge Graph", "ko": "지식 그래프"},
    "dock_sandbox_title": {"en": "Mathematical Verification Sandbox", "ko": "수치 검증 및 계산 샌드박스"},
    "menu_mobile_server": {"en": "Mobile LAN Server...", "ko": "모바일 LAN 미러 서버..."},
    "menu_vault_backup": {"en": "Encrypted Vault Backup...", "ko": "암호화 금고 백업/복원..."},
    "gap_fill_title": {"en": "Autonomous Gap-Fill Addendum", "ko": "자율 심층 보완 탐색 결과"},
    "server_pin_label": {"en": "Access PIN: {pin}", "ko": "접속 인증 PIN: {pin}"},
    "btn_run_sandbox": {"en": "Execute & Verify", "ko": "코드 실행 및 검증"},
    "btn_gap_fill_toggle": {"en": "Recursive Gap-Filling (Auto-Deepening)", "ko": "자율 심층 보완 탐색"},
    "btn_insert_plot": {"en": "Insert Plot to Report", "ko": "보고서에 수치 검증 결과 삽입"},
    "sandbox_terminal_title": {"en": "Sandbox Execution Console", "ko": "샌드박스 실행 콘솔"},
    "sandbox_plot_title": {"en": "Generated Matplotlib Visualizations", "ko": "생성된 시각화 플롯"},
    "vault_dialog_title": {"en": "Zero-Knowledge Encrypted Vault (AES-256-GCM)", "ko": "영지식 암호화 금고 백업 및 복원 (AES-256-GCM)"},
    "vault_pwd_label": {"en": "Master Passphrase:", "ko": "마스터 암호:"},
    "vault_backup_btn": {"en": "Backup Now (.omni.vault)", "ko": "즉시 금고 암호화 백업"},
    "vault_restore_btn": {"en": "Decrypt & Restore", "ko": "금고에서 복원"},
    "mobile_dialog_title": {"en": "Mobile LAN Web Mirror", "ko": "모바일 로컬 네트워크 미러"},
    "mobile_server_running": {"en": "Server is live on LAN", "ko": "로컬 네트워크 서버 실행 중"},
    "mobile_qr_instructions": {"en": "Scan QR code or open URL in any browser on the same Wi-Fi:", "ko": "동일 Wi-Fi 내 스마트폰 브라우저로 QR 코드를 스캔하거나 URL에 접속하세요:"},
    "graph_filter_placeholder": {"en": "Filter entities by name or category...", "ko": "엔티티 이름 또는 범주 필터..."},
    "graph_legend_label": {"en": "Legend: Organization | Program | Key Figure | Standard | Material", "ko": "범례: 기관/기업 | 프로그램 | 핵심 인물 | 기술 표준 | 소재/합금"},

    # Phase 12: Stabilization, Settings Persistence & Resource Lifecycle
    "menu_preferences": {"en": "Preferences...", "ko": "환경 설정..."},
    "menu_edit": {"en": "Edit", "ko": "편집"},
    "settings_dialog_title": {"en": "Workstation Preferences", "ko": "워크스테이션 환경 설정"},
    "tab_settings_general": {"en": "General / API", "ko": "일반 및 API"},
    "tab_settings_models": {"en": "Models & Local LLM", "ko": "모델 및 로컬 LLM"},
    "tab_settings_audio": {"en": "Audio & Media", "ko": "오디오 및 미디어"},
    "tab_settings_network": {"en": "Network & LAN Mirror", "ko": "네트워크 및 LAN 미러"},
    "tab_settings_storage": {"en": "Storage & Vault", "ko": "저장소 및 암호화 금고"},
    "btn_apply": {"en": "Apply", "ko": "적용"},
    "btn_save": {"en": "Save Preferences", "ko": "설정 저장"},
    "settings_saved_msg": {"en": "Preferences saved and applied immediately.", "ko": "설정이 성공적으로 저장 및 적용되었습니다."},

    # Bilingual Workspace View Controls
    "btn_view_original": {"en": "View Original", "ko": "원문 보기"},
    "btn_view_translation": {"en": "View Translation", "ko": "번역본 보기"},

    # Exporter Labels & Tables
    "title": {"en": "Grounded Synthesis Report", "ko": "출처 기반 종합 보고서"},
    "generated": {"en": "Generated", "ko": "생성 일시"},
    "model": {"en": "Model", "ko": "모델"},
    "groundedness": {"en": "Groundedness", "ko": "근거 일치율"},
    "verified": {"en": "Verified", "ko": "검증됨"},
    "bibliography": {"en": "Bibliography", "ko": "참고 문헌"},
    "col_ref": {"en": "Ref", "ko": "번호"},
    "col_source": {"en": "Source", "ko": "출처"},
    "col_location": {"en": "Location / URL", "ko": "위치 / URL"},
    "theme_toggle": {"en": "Toggle theme", "ko": "테마 전환"},
    "generated_by": {"en": "Generated by OmniResearch Studio", "ko": "OmniResearch Studio 생성"},

    # Compute & Hardware Acceleration Dialog
    "compute_dialog_title": {"en": "Compute & Hardware Acceleration", "ko": "연산 및 하드웨어 가속 설정"},
    "compute_active_provider": {"en": "Active Execution Provider:", "ko": "활성 실행 프로바이더:"},
    "compute_thread_count": {"en": "Device Thread Count:", "ko": "디바이스 스레드 수:"},
    "compute_quantization": {"en": "Quantization Precision:", "ko": "양자화 정밀도:"},
    "compute_onnx_providers": {"en": "Available ONNX Providers:", "ko": "사용 가능한 ONNX 프로바이더:"},
    "compute_btn_switch": {"en": "Switch Provider", "ko": "프로바이더 변경"},
    "compute_status_applied": {"en": "Compute profile applied immediately.", "ko": "연산 프로필이 즉시 적용되었습니다."},
    "compute_hardware_info": {"en": "Hardware Acceleration Details", "ko": "하드웨어 가속 세부 정보"},
    "compute_vulkan": {"en": "Vulkan GPU (FP32)", "ko": "Vulkan GPU 가속 (FP32)"},

    # Worker Telemetry Localization & Timeout Diagnostics
    "omnisweep_phase_1": {"en": "[1/4] Initializing OmniSweep discovery...", "ko": "[1/4] 다각도 웹 탐색 초기화 중..."},
    "omnisweep_phase_2": {"en": "[2/4] Executing perspective search queries...", "ko": "[2/4] 관점별 세부 웹 검색 실행 중..."},
    "omnisweep_phase_3": {"en": "[3/4] Ingesting and extracting source passages...", "ko": "[3/4] 참조 소스 본문 추출 및 분석 중..."},
    "omnisweep_phase_4": {"en": "[4/4] Synthesizing multi-perspective perspective report...", "ko": "[4/4] 다각도 종합 보고서 생성 중..."},
    "status_ready": {"en": "Ready", "ko": "대기 중"},
    "timeout_dialog_title": {"en": "Task Execution Timed Out", "ko": "작업 시간 초과"},
    "timeout_dialog_header": {"en": "[OmniSweep Watchdog] Operation aborted due to lack of network activity (>60s).", "ko": "[OmniSweep 워치독] 네트워크 응답이 60초 이상 지연되어 작업을 안전하게 중단했습니다."},
    "timeout_dialog_causes": {
        "en": "Potential Root Causes:\n1. Google Gemini API network congestion or rate-limit throttling.\n2. Active API key quota exhausted or invalid token permissions.\n3. Intermittent DNS resolution failure or packet loss during source scraping.\n4. Firewall, VPN, or proxy intercepting persistent TLS socket streams.",
        "ko": "예상 원인:\n1. Google Gemini API 네트워크 지연 또는 요청 한도 초과.\n2. API 키 할당량 소진 또는 권한 설정 문제.\n3. 소스 스크래핑 중 일시적 DNS 확인 실패 또는 패킷 손실.\n4. 방화벽, VPN 또는 프록시 환경의 연결 차단.",
    },
    "timeout_dialog_recommendations": {
        "en": "Recommendations:\n• Verify your internet connection.\n• Inspect quota in Google AI Studio.\n• Retry with a refined topic prompt.",
        "ko": "해결 권장사항:\n• 인터넷 연결 상태를 확인하세요.\n• Google AI Studio에서 사용량 및 할당량을 확인하세요.\n• 검색 주제나 프롬프트를 조정한 후 다시 시도하세요.",
    },

    # Action Control Tooltips (Bilingual QToolTip Support)
    "tooltip_add_files": {
        "en": "Import local research files (.pdf, .txt, .md) into the active workspace corpus.",
        "ko": "로컬 연구 문서(.pdf, .txt, .md)를 현재 워크스페이스 코퍼스로 가져옵니다.",
    },
    "tooltip_diff_compare": {
        "en": "Analyze semantic differences and overlapping claims between checked documents.",
        "ko": "선택한 문서 간 의미적 차이점 및 중복 주장을 비교 분석합니다.",
    },
    "tooltip_clear_all": {
        "en": "Remove all loaded source documents from the current project.",
        "ko": "현재 프로젝트에서 불러온 모든 소스 문서를 제거합니다.",
    },
    "tooltip_run_discovery": {
        "en": "Execute multi-perspective Google Search grounding across enabled expert lenses.",
        "ko": "선택된 전문가 관점을 기반으로 다각도 Google 검색 그라운딩을 실행합니다.",
    },
    "tooltip_synthesize": {
        "en": "Generate an epistemically balanced, zero-temperature synthesis citing verified corpus sources.",
        "ko": "검증된 코퍼스 출처를 인용하여 인식론적으로 균형 잡힌 무작위성 0(Zero-Temperature) 종합 보고서를 생성합니다.",
    },
    "tooltip_gap_fill": {
        "en": "Automatically detect knowledge gaps and execute up to 2 targeted follow-up queries.",
        "ko": "지식 격차를 자동 탐지하고 최대 2회의 심화 질의를 순환 실행합니다.",
    },
    "tooltip_export_report": {
        "en": "Export the finalized report to Markdown, HTML, or structured JSON.",
        "ko": "완성된 보고서를 Markdown, HTML 또는 구조화된 JSON으로 내보냅니다.",
    },
    "tooltip_split_view": {
        "en": "Toggle side-by-side workspace comparison between perspectives or iterations.",
        "ko": "관점 간 또는 반복 작업 결과 간 좌우 분할 비교 뷰를 전환합니다.",
    },
    "tooltip_auto_layout": {
        "en": "Recalculate node cluster coordinates and auto-fit the full graph within view.",
        "ko": "노드 군집 좌표를 재계산하고 전체 그래프를 뷰포트 크기에 맞춥니다.",
    },
    "tooltip_export_svg": {
        "en": "Export the current directed vector graph as a scalable SVG graphic.",
        "ko": "현재 방향성 벡터 그래프를 고해상도 SVG 벡터 파일로 내보냅니다.",
    },
    "tooltip_zoom_in": {
        "en": "Zoom graph viewport in or out (Mouse wheel zoom is also supported).",
        "ko": "그래프 뷰포트를 확대/축소합니다 (마우스 휠 스크롤로도 가능).",
    },
    "tooltip_zoom_out": {
        "en": "Zoom graph viewport in or out (Mouse wheel zoom is also supported).",
        "ko": "그래프 뷰포트를 확대/축소합니다 (마우스 휠 스크롤로도 가능).",
    },
    "tooltip_cancel_task": {
        "en": "Immediately interrupt active network requests and abort background workers.",
        "ko": "활성 네트워크 요청을 즉시 중단하고 백그라운드 작업을 안전하게 취소합니다.",
    },
    "tooltip_filter_entities": {
        "en": "Type to filter nodes by entity name or category (Organization, Concept, etc.).",
        "ko": "엔티티 이름 또는 범주(조직, 개념 등)로 노드를 필터링합니다.",
    },
    "tooltip_enable_all": {
        "en": "Include all corpus documents in synthesis and analysis.",
        "ko": "모든 코퍼스 문서를 종합 분석에 포함합니다.",
    },
    "tooltip_disable_all": {
        "en": "Exclude all corpus documents from synthesis.",
        "ko": "모든 문서를 분석 대상에서 일시 제외합니다.",
    },
    "tooltip_remove_selected": {
        "en": "Remove the currently selected document from the corpus.",
        "ko": "선택한 문서를 코퍼스에서 제거합니다.",
    },
    "tooltip_toggle_translation": {
        "en": "Toggle between the original English report and Korean translation.",
        "ko": "원문과 번역본 뷰를 상호 전환합니다.",
    },
    "tooltip_chat_toggle": {
        "en": "Expand or collapse the interactive follow-up research drawer.",
        "ko": "심층 질의응답 및 후속 연구 대화창을 열거나 접습니다.",
    },
    "tooltip_chat_clear": {
        "en": "Clear the entire conversation history in this workspace.",
        "ko": "현재 워크스페이스의 대화 기록을 초기화합니다.",
    },
    "tooltip_chat_send": {
        "en": "Submit your research question to the grounded synthesis engine.",
        "ko": "근거 기반 종합 분석 엔진에 후속 질의를 제출합니다.",
    },
    "tooltip_generate_audio": {
        "en": "Generate a dual-host podcast dialogue script from the report.",
        "ko": "보고서 내용을 기반으로 2인 팟캐스트 대화 대본을 작성합니다.",
    },
    "tooltip_export_audio_script": {
        "en": "Save the dialogue script as a text file (.txt).",
        "ko": "대화 대본을 텍스트 파일(.txt)로 내보냅니다.",
    },
    "tooltip_render_audio": {
        "en": "Synthesize dialogue audio using the faster-whisper/TTS pipeline.",
        "ko": "생성된 대본을 고품질 음성 오디오(.mp3)로 렌더링합니다.",
    },
    "tooltip_play_audio": {
        "en": "Play or pause the generated audio briefing.",
        "ko": "오디오 브리핑을 재생하거나 일시 정지합니다.",
    },
    "tooltip_save_audio": {
        "en": "Save the rendered MP3 audio briefing to disk.",
        "ko": "렌더링된 MP3 오디오 파일을 저장합니다.",
    },
    "tooltip_open_url": {
        "en": "Open the source document or grounding link in your default web browser.",
        "ko": "기본 웹 브라우저에서 원본 문서 또는 웹 링크를 엽니다.",
    },
    "tooltip_mobile_server": {
        "en": "Launch the Mobile LAN Live Mirror server to view reports on mobile devices.",
        "ko": "모바일 기기에서 실시간으로 연구 보고서를 확인하는 로컬 서버를 엽니다.",
    },
    "tooltip_change_api_key": {
        "en": "Configure or update your Google Gemini API key securely in Windows Credential Vault.",
        "ko": "Windows 보안 자격 증명 관리자에 Gemini API 키를 등록하거나 변경합니다.",
    },
    "tooltip_reset_zoom": {
        "en": "Reset graph view scale and center viewport.",
        "ko": "그래프 배율을 기본값으로 초기화하고 중앙에 맞춥니다.",
    },
    "tooltip_find_close": {
        "en": "Close the in-page search bar (Escape).",
        "ko": "보고서 내 단어 찾기 검색창을 닫습니다 (Esc).",
    },
    "tooltip_split_close": {
        "en": "Close the side-by-side split comparison view.",
        "ko": "좌우 분할 비교 뷰를 닫습니다.",
    },
    "tooltip_run_sandbox": {
        "en": "Execute the Python calculation script in a secure sandbox.",
        "ko": "보안 샌드박스 환경에서 파이썬 계산 스크립트를 실행합니다.",
    },
    "tooltip_insert_plot": {
        "en": "Insert the generated mathematical plot into the active synthesis report.",
        "ko": "생성된 수학/통계 그래프를 종합 보고서 본문에 삽입합니다.",
    },
    "tooltip_source_prev": {
        "en": "Navigate to the previous document in the corpus.",
        "ko": "코퍼스 내 이전 문서로 이동합니다.",
    },
    "tooltip_source_next": {
        "en": "Navigate to the next document in the corpus.",
        "ko": "코퍼스 내 다음 문서로 이동합니다.",
    },
    "tooltip_discovery_model": {
        "en": "Select the Gemini model utilized for multi-perspective search grounding.",
        "ko": "다각도 웹 검색 그라운딩에 사용할 Gemini 모델을 선택합니다.",
    },
    "tooltip_synthesis_model": {
        "en": "Select the Gemini model utilized for grounded report synthesis.",
        "ko": "근거 기반 종합 보고서 작성에 사용할 Gemini 모델을 선택합니다.",
    },
    "tooltip_compression_mode": {
        "en": "Configure context compression mode to manage token limits and throughput.",
        "ko": "토큰 한도 및 처리 속도 최적화를 위한 컨텍스트 압축 모드를 설정합니다.",
    },
    "tooltip_language_select": {
        "en": "Switch application UI and report translation language.",
        "ko": "애플리케이션 인터페이스 및 보고서 표시 언어를 전환합니다.",
    },
    "tooltip_search_fts": {
        "en": "Search corpus documents using full-text search index (FTS5).",
        "ko": "전문 검색 색인(FTS5)을 사용하여 코퍼스 문서를 검색합니다.",
    },
    "tooltip_vision_analyze": {
        "en": "Perform multimodal AI visual inspection and diagram analysis.",
        "ko": "다중 모달 AI를 통해 시각적 다이어그램 및 이미지 분석을 수행합니다.",
    },
    "tooltip_scroll_left": {
        "en": "Scroll tabs left",
        "ko": "탭 목록 왼쪽으로 스크롤",
    },
    "tooltip_scroll_right": {
        "en": "Scroll tabs right",
        "ko": "탭 목록 오른쪽으로 스크롤",
    },
    "tooltip_clear_field": {
        "en": "Clear input field",
        "ko": "입력 내용 지우기",
    },
    "tooltip_menu_more": {
        "en": "More menu options",
        "ko": "추가 메뉴 항목",
    },
}

import logging
import re

logger = logging.getLogger("Omni_i18n")


def humanize_key(key: str) -> str:
    """Format an unlocalized key into a clean, human-readable string by stripping code prefixes."""
    cleaned = re.sub(r"^(btn_|lbl_|txt_|menu_|title_|tab_|action_|col_|sec\d+_|dialog_)", "", key)
    words = cleaned.replace("_", " ").replace("-", " ").strip()
    return words.title() if words else key


def get_text(key: str, lang: str = "en") -> str:
    """
    Resolve localized string with robust fallback chain:
    1. Target language in STRINGS (e.g., 'ko')
    2. Default language (English 'en')
    3. Humanized key name (e.g., 'btn_view_translation' -> 'View Translation')
    Emits debug/warning logging whenever a fallback occurs.
    """
    if not key or not isinstance(key, str):
        return ""

    target_lang = "ko" if lang.startswith("ko") else "en"
    key_entry = STRINGS.get(key)

    if key_entry is not None:
        # 1. Target language match
        if target_lang in key_entry and key_entry[target_lang]:
            return key_entry[target_lang]

        # 2. Default language (English) fallback
        if "en" in key_entry and key_entry["en"]:
            logger.debug(f"[i18n Warning] Missing translation key: {key} for locale: {target_lang} (fallback to English)")
            return key_entry["en"]

    # 3. Defensive Humanized Key Fallback
    logger.warning(f"[i18n Warning] Missing translation key: {key} for locale: {target_lang}")
    return humanize_key(key)


# Convenience aliases
tr = get_text
t = get_text
