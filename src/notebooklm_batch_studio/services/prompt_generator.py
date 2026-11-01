"""Prompt generator for academic consistency and topic-specific artifact synthesis.

Implements the Master Style Blueprint for university senior and graduate level standards,
leveraging local Ollama (gemma4) via domain protocol with offline rule-based fallback.
"""

from __future__ import annotations

import logging

from notebooklm_batch_studio.domain.models import ArtifactType
from notebooklm_batch_studio.domain.repositories import OllamaClientProtocol

logger = logging.getLogger(__name__)

# Master Style Blueprint: System rules applied across all chapters to maintain style consistency
MASTER_STYLE_SYSTEM_PROMPT = """你是一位熟悉本課程領域、具備豐富大學教學經驗的教授。
你的任務是根據特定的章節主題與產出物類型，為 Google NotebookLM 撰寫精準、具學術水準的提示詞。
核心規範：
1. 難度定位：依各產出要求的難度出題，著重觀念辨析與應用。
2. 語言規範：一律使用繁體中文 (zh-TW)，專有名詞在首次出現時須以括號附註英文原名。
3. 風格一致性：格式結構需嚴謹統一，禁止出現過度口語或風格斷層的語調。
4. 選項規範（針對測驗）：四個選項長度相仿、各具理論誘答力，禁止使用「以上皆是」或「以上皆非」。
請直接輸出給 NotebookLM 的具體指示 Prompt，長度約 150~250 字，不要有多餘客套話。"""


def _get_quiz_prompts(base_rules: str) -> dict[str, str]:
    """Build blueprint prompts for quiz artifacts.

    Args:
        base_rules: Common academic instructions prefix.

    Returns:
        Mapping of quiz artifact types to prompt text.
    """
    return {
        # Every quiz asks for 30 questions: the runner needs 30, and asking for fewer forces
        # extra generation batches (duplicate titles, wasted quota). Wording is subject-neutral.
        ArtifactType.QUIZ_ACADEMIC.value: (
            f"{base_rules}請根據本講義生成 30 題【學術精研測驗 (Academic Advanced Quiz)】單選題。"
            "難度為研究所／大學高年級：比較不同理論或做法的優缺點、分析與批判論證、"
            "在複雜情境中推理判斷、跨概念整合。"
            "每題提供 4 個長度相仿且具誘答力之選項，標明正解並提供深度解析與講義依據。"
        ),
        ArtifactType.QUIZ_CONCEPT.value: (
            f"{base_rules}請根據本講義生成 30 題【概念刷題測驗 (Concept Drill Quiz)】單選題。"
            "著重快速檢查觀念：關鍵名詞定義、容易混淆的概念比較、流程或步驟的順序、核心原理。"
            "每題提供 4 個選項，題幹精簡明確，標明正解並附觀念診斷解析。"
        ),
        ArtifactType.QUIZ_1.value: (
            f"{base_rules}請根據本講義生成 30 題【測驗 1 - 基礎記憶與核心定義】單選題。"
            "著重本講的重要名詞、定義、基本事實與基本原理，確認是否記得並分得清楚。"
            "每題提供 4 個長度相仿且具誘答力的選項，標明正確答案並附詳細解析與講義依據。"
        ),
        ArtifactType.QUIZ_2.value: (
            f"{base_rules}請根據本講義生成 30 題【測驗 2 - 理解與應用】單選題。"
            "題幹必須放進具體情境或例子，考核能否用本講的概念解釋現象、選擇合適做法或判斷結果。"
            "每題提供 4 個長度相仿之選項，標明答案並提供深度解析。"
        ),
        ArtifactType.QUIZ_3.value: (
            f"{base_rules}請根據本講義生成 30 題【測驗 3 - 模擬考】高難度單選題。"
            "模擬正式考試：綜合多個概念、比較易混淆觀念、分析限制與例外、需要多步推理的題目。"
            "選項應具高度辨析度，詳細說明正確理由與各干擾選項錯在哪裡。"
        ),
    }


def _get_chapter_prompts(base_rules: str) -> dict[str, str]:
    """Build blueprint prompts for lecture-level artifacts.

    Args:
        base_rules: Common academic instructions prefix.

    Returns:
        Mapping from artifact type value to prompt text.
    """
    prompts = _get_quiz_prompts(base_rules)
    prompts.update(
        {
            ArtifactType.FLASHCARDS.value: (
                f"{base_rules}請萃取 30~50 個核心研究法與統計專有名詞重點閃卡 (Flashcards)。"
                "正面為專有名詞與簡短核心情境提問，背面為精確學術定義、實驗範例與方法學陷阱提示。"
            ),
            ArtifactType.MIND_MAP.value: (
                f"{base_rules}請為本講義梳理完整的多層級【知識架構心智圖 (Mind Map)】。"
                "包含：核心研究問題 ➔ 理論背景 ➔ 研究方法與變項操作 ➔ 效度威脅與倫理 ➔ 結論延伸。"
            ),
            ArtifactType.STUDY_GUIDE.value: (
                f"{base_rules}請撰寫本章【精讀讀書指南 (Study Guide)】。"
                "包含章節學習目標、核心概念精要、方法學優缺點比較矩陣與 3 個延伸研討思考題。"
            ),
            ArtifactType.SLIDE_DECK.value: (
                f"{base_rules}請生成結構嚴謹的【專題報告投影片大綱 (Slide Deck)】。"
                "依序包含：研究背景動機、核心概念架構、研究方法設計、實證分析與學術批判。"
            ),
            ArtifactType.INFOGRAPHIC.value: (
                f"{base_rules}請輸出適合轉化為資訊圖表 (Infographic) 的結構化視覺文本摘要。"
                "包含研究流程圖步驟、核心數據指標、概念對比圖表與關鍵警示提醒。"
            ),
            ArtifactType.DATA_TABLE.value: (
                f"{base_rules}請生成全方位【概念與方法比較分析資料表 (Data Table)】。"
                "使用 Markdown 格式呈現各研究方法之適用情境、優點、局限性與典型範例。"
            ),
            ArtifactType.VIDEO.value: (
                f"{base_rules}請撰寫適合劇院影音或學術 Podcast 導讀之劇本講稿 (Video Script)。"
                "以專業學者對談口吻，生動引導閱聽者掌握本章研究方法之精髓與爭議點。"
            ),
            ArtifactType.REPORTS_BRIEFING.value: (
                f"{base_rules}請根據本講義撰寫【高階研究摘要報告 (Briefing Doc)】。"
                "包含 Executive Summary（執行摘要）、核心學術發現、重要論點引述、實證結論分析與關鍵洞察。"
            ),
            ArtifactType.REPORTS_STUDY_GUIDE.value: (
                f"{base_rules}請根據本講義撰寫【綜合研讀指南 (Synthesis Study Guide)】。"
                "包含核心知識點總覽、十題簡答檢驗題與解答、五項深度研討思考題，以及專有名詞辭典。"
            ),
            ArtifactType.REPORTS_BLOG_POST.value: (
                f"{base_rules}請根據本講義撰寫【學術知識精華文章 (Blog Post)】。"
                "以清晰流暢風格萃取本講義最具突破性之核心觀念，使用小標題與重點引言整理成高品質知識長文。"
            ),
            ArtifactType.REPORTS_CONCEPT.value: (
                f"{base_rules}請根據本講義撰寫【概念解說 (Concept Explanation)】。"
                "逐一解釋本講最重要的概念：白話定義、為什麼重要、具體例子、常見誤解，以及概念之間的關係。"
            ),
        }
    )
    return prompts


def _get_course_prompts(course_name: str, lang_instruction: str) -> dict[str, str]:
    """Build blueprint prompts for course-wide aggregated artifacts.

    Args:
        course_name: Course title.
        lang_instruction: Language constraint clause.

    Returns:
        Mapping from course artifact type value to prompt text.
    """
    return {
        ArtifactType.COURSE_MOCK_EXAM.value: (
            f"本課程為【{course_name}】全範圍綜合期末考。難度設定為期末考水準，簡單、中等、困難題目都要有。"
            f"{lang_instruction}請生成 50 題跨章節整合單選題，涵蓋各章核心概念與跨章節的綜合應用。"
            "每題附詳細學術解析、診斷提示與各選項辨析。"
        ),
        ArtifactType.COURSE_QUIZ_ACADEMIC.value: (
            f"本課程為【{course_name}】全範圍學術精研期末考。難度設定為研究所入學考水準。"
            f"{lang_instruction}請生成 50 題跨章節深度學術單選題，著重跨概念統整、理論比較與批判分析。"
            "每題附完整解析與選項理論辨析。"
        ),
        ArtifactType.COURSE_QUIZ_CONCEPT.value: (
            f"本課程為【{course_name}】全範圍核心觀念刷題考。"
            f"{lang_instruction}請生成 50 題跨章節核心觀念刷題單選題，快速檢驗各章定義、機制與關鍵考點。"
            "題幹精準簡潔，附重點診斷解析。"
        ),
        ArtifactType.COURSE_MIND_MAP.value: (
            f"本課程為【{course_name}】。{lang_instruction}請繪製貫穿全部講義之【全課程總架構心智圖】。"
            "展示從科學研究本質、假說建立、研究設計、變項測量至效度與倫理之知識地圖。"
        ),
        ArtifactType.COURSE_STUDY_GUIDE.value: (
            f"本課程為【{course_name}】。{lang_instruction}請彙編【全課程總結讀書指南】。"
            "整合各章核心關聯、全書方法學對照比較與期末核心考點精華整理。"
        ),
        ArtifactType.COURSE_AUDIO.value: (
            f"本課程為【{course_name}】。{lang_instruction}請產出全課程總回顧語音導讀腳本。"
            "貫穿全學期的知識體系，串聯各章關鍵概念與核心思維。"
        ),
        ArtifactType.COURSE_REPORTS_BRIEFING.value: (
            f"本課程為【{course_name}】全範圍學術總結報告。{lang_instruction}"
            "請撰寫全課程高階研究摘要報告 (Briefing Doc)。"
            "整合全學期核心理論體系、關鍵實證發現與研究方法學總體評析。"
        ),
        ArtifactType.COURSE_REPORTS_STUDY_GUIDE.value: (
            f"本課程為【{course_name}】全範圍期末總複習指南。{lang_instruction}"
            "請撰寫綜合研讀指南 (Synthesis Study Guide)。"
            "包含全書概念架構、跨章節檢驗題、綜合討論題與全課程專有名詞辭典。"
        ),
        ArtifactType.COURSE_REPORTS_BLOG_POST.value: (
            f"本課程為【{course_name}】。{lang_instruction}請撰寫全課程知識精華文章 (Blog Post)。"
            "以引人入勝的文章風格統整本門課最有啟發性的十項核心研究原則與思維精要。"
        ),
        ArtifactType.COURSE_REPORTS_CONCEPT.value: (
            f"本課程為【{course_name}】。{lang_instruction}請撰寫全課程概念解說 (Concept Explanation)。"
            "整理跨章節最核心的概念：白話定義、例子、常見誤解，並說明概念如何串連成整門課的知識架構。"
        ),
    }


class PromptGenerator:
    """Generates standardized academic prompts for NotebookLM artifacts."""

    def __init__(self, ollama_client: OllamaClientProtocol | None = None) -> None:
        """Initialize the prompt generator.

        Args:
            ollama_client: Optional Ollama client instance.
        """
        self.ollama = ollama_client

    def get_base_blueprint_prompt(
        self,
        artifact_type: ArtifactType | str,
        topic: str,
        course_name: str,
        language: str = "zh-TW",
    ) -> str:
        """Generate deterministic rule-based blueprint prompt for artifact.

        Args:
            artifact_type: The artifact type enum or string value.
            topic: Chapter topic or course range description.
            course_name: Full course title.
            language: Target language (zh-TW, en, bilingual).

        Returns:
            Structured prompt string matching the master academic blueprint.
        """
        type_val = artifact_type.value if isinstance(artifact_type, ArtifactType) else str(artifact_type)
        lang_instruction = "請一律以標準繁體中文 (zh-TW) 輸出，重要專有名詞於括號附註英文。"
        if language == "en":
            lang_instruction = "Please output strictly in formal academic English."
        elif language == "bilingual":
            lang_instruction = "請採用中英雙語對照輸出 (Traditional Chinese and English bilingual format)。"

        base_rules = f"本講義主題為【{course_name} — {topic}】。{lang_instruction} "

        all_prompts = _get_chapter_prompts(base_rules)
        all_prompts.update(_get_course_prompts(course_name, lang_instruction))

        return all_prompts.get(type_val, f"{base_rules}請為【{topic}】生成高品質學術產出物。")

    def generate_refined_prompt(
        self,
        artifact_type: ArtifactType | str,
        topic: str,
        course_name: str,
        language: str = "zh-TW",
        use_ollama: bool = True,
    ) -> str:
        """Generate customized prompt using Ollama gemma4 with blueprint fallback.

        Args:
            artifact_type: Artifact type enum or string.
            topic: Chapter topic or scope.
            course_name: Course title.
            language: Target output language.
            use_ollama: Whether to attempt Ollama enhancement.

        Returns:
            Refined prompt string.
        """
        base_prompt = self.get_base_blueprint_prompt(artifact_type, topic, course_name, language)
        if not use_ollama or self.ollama is None:
            return base_prompt

        user_req = (
            f"課程：{course_name}\n講義章節主題：{topic}\n產出物類型：{artifact_type}\n"
            f"基礎母版指引：{base_prompt}\n"
            "請根據上述資訊，潤飾並擴充一份語氣嚴謹、符合研究所高標準學術水準的具體 Prompt 指令。"
        )

        try:
            enhanced = self.ollama.generate(prompt=user_req, system_prompt=MASTER_STYLE_SYSTEM_PROMPT)
            if enhanced and len(enhanced) >= 40:
                logger.info("Successfully generated refined prompt via Ollama gemma4 for %s", topic)
                return enhanced
        except Exception as err:
            logger.warning("Ollama prompt refinement failed, using blueprint prompt: %s", err)

        return base_prompt
