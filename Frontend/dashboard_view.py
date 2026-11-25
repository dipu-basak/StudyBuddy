import asyncio
import os
import re
from datetime import datetime
import flet as ft
from api_client import api_client
from theme import (
    BG_COLOR, CARD_BG, CARD_BG_MUTED, INSET_BG, PRIMARY_TEAL, 
    PRIMARY_TEAL_DARK, PRIMARY_TEAL_LIGHT, PRIMARY_TEAL_BORDER,
    ACCENT_ORANGE, ACCENT_ORANGE_DARK, ACCENT_ORANGE_LIGHT, ACCENT_ORANGE_BORDER,
    TEXT_TITLE, TEXT_BODY, TEXT_MUTED, TEXT_LIGHT, BORDER_COLOR, 
    CARD_SHADOW, SOFT_SHADOW, soft_card
)

class DashboardView:
    def __init__(self, page: ft.Page, user_data: dict, on_logout, token: str = None):
        self.page = page
        self.user = user_data or {}
        self.on_logout = on_logout
        self.token = token

        # ── State Variables ──────────────────────────────────────
        self.selected_mode = "both"  # "summary", "quiz", "both"
        self.selected_quiz_count = 5 # 3, 5, 10, 15
        self.mega_quiz_mode = False  # Toggle for multi-session Mega Quiz selection
        self.mega_quiz_selected_ids = set() # Set of selected session IDs for Mega Quiz
        self.upload_type = "file"    # "file", "text"
        self.active_nav = "Workspace"
        self.selected_file_name = None
        self.selected_file_size = None
        self.uploaded_file_id = None
        self.is_generating = False

        # AI Study Session State
        self.current_session = None      # Dict with summary, quiz, topic, session_id
        self.history_items = []          # List of past generated study sessions
        self.center_mode = "workspace"   # "workspace", "summary", "quiz", "review"
        self.quiz_current_index = 0
        self.quiz_selected_answers = {}  # {question_index: selected_option_index}
        self.quiz_total_timer_seconds = 300 # Scaled based on question count
        self.quiz_timer_seconds = 300    # Countdown seconds
        self.quiz_timer_running = False
        self.quiz_timer_task = None
        self.quiz_results = None

        # File Picker setup (Flet 1.0+ service)
        self.file_picker = ft.FilePicker(on_result=self._on_file_picked)
        if hasattr(self.page, "services") and self.file_picker not in self.page.services:
            self.page.services.append(self.file_picker)

        # ── Reactive UI References ───────────────────────────────
        self.topic_input = ft.TextField(
            hint_text="e.g. Cellular Respiration, CS Algorithms Midterm, Organic Chem Ch. 4",
            border_radius=12,
            bgcolor=INSET_BG,
            border_color=BORDER_COLOR,
            focused_border_color=PRIMARY_TEAL,
            text_size=13,
            dense=True,
            content_padding=ft.Padding(14, 12, 14, 12),
        )

        self.notes_paste_input = ft.TextField(
            hint_text="Paste your lecture notes, transcript, or summary text here...",
            border_radius=12,
            bgcolor=INSET_BG,
            border_color=BORDER_COLOR,
            focused_border_color=PRIMARY_TEAL,
            text_size=13,
            multiline=True,
            min_lines=6,
            max_lines=8,
            visible=False,
            on_change=self._on_notes_changed,
        )

        self.notes_word_count = ft.Text("0 words • 0 characters", size=11, color=TEXT_LIGHT, visible=False)

        self.mode_subtext = ft.Text(
            "Displays the 30-min summary first, then seamlessly unlocks the 5-min timed quiz.",
            size=12,
            color=TEXT_MUTED,
            text_align=ft.TextAlign.CENTER,
        )

        self.file_status_text = ft.Text(
            "",
            size=12,
            weight=ft.FontWeight.W_600,
            color=PRIMARY_TEAL,
            visible=False,
        )

        # Dynamic Nav references
        self.nav_workspace_btn = None
        self.nav_history_btn = None
        self.nav_achievements_btn = None
        self.nav_pro_btn = None

        # Dynamic stat pill text references
        self.streak_pill_text = None
        self.xp_pill_text = None
        self.quota_pill_text = None

        # Mode card references
        self.mode_summary_card = None
        self.mode_quiz_card = None
        self.mode_both_card = None

        # Upload type button references
        self.upload_doc_btn = None
        self.upload_paste_btn = None
        self.dropzone_container = None
        self.paste_upload_btn = None
        self.generate_session_btn = None

        # Main Layout Dynamic Column Containers
        self.center_card_container = ft.Container()
        self.left_history_container = ft.Container()
        self.right_achievements_container = ft.Container()

    # ── Notification Helper (stays on dashboard) ────────────────
    def _notify(self, message: str, is_info: bool = True):
        snack = ft.SnackBar(
            content=ft.Row([
                ft.Icon(ft.Icons.CHECK_CIRCLE if is_info else ft.Icons.INFO_OUTLINE, color=ft.Colors.WHITE, size=18),
                ft.Text(message, color=ft.Colors.WHITE, size=13, weight=ft.FontWeight.W_500),
            ], spacing=10),
            bgcolor=PRIMARY_TEAL if is_info else ACCENT_ORANGE_DARK,
            behavior=ft.SnackBarBehavior.FLOATING,
            duration=3000,
        )
        self.page.overlay.append(snack)
        snack.open = True
        self.page.update()

    # ── File Handling & Security Verification ───────────────────
    async def _on_file_picked(self, e: ft.FilePickerResultEvent):
        if e.files and len(e.files) > 0:
            picked = e.files[0]
            file_bytes = None
            
            if hasattr(picked, "bytes") and picked.bytes is not None:
                file_bytes = picked.bytes
            elif hasattr(picked, "path") and picked.path:
                try:
                    def _read_file():
                        with open(picked.path, "rb") as f:
                            return f.read()
                    file_bytes = await asyncio.to_thread(_read_file)
                except Exception:
                    pass
            
            if file_bytes is not None:
                await self._upload_and_apply_file(picked.name, file_bytes)
            else:
                self._notify("Could not read selected file bytes.", is_info=False)

    async def _handle_browse_click(self, _):
        # 1. Attempt FilePicker service with bytes data
        try:
            files = await self.file_picker.pick_files(
                dialog_title="Select Lecture Slides or Notes",
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["pdf", "png", "jpg", "jpeg", "webp", "txt"],
                with_data=True
            )
            if files and len(files) > 0:
                picked = files[0]
                file_bytes = getattr(picked, "bytes", None)
                if not file_bytes and getattr(picked, "path", None):
                    with open(picked.path, "rb") as f:
                        file_bytes = f.read()
                if file_bytes:
                    await self._upload_and_apply_file(picked.name, file_bytes)
                    return
        except Exception:
            pass

        # 2. Native OS file dialog fallback
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            filepath = filedialog.askopenfilename(
                title="Select Lecture Slides or Notes",
                filetypes=[
                    ("Supported Lecture Documents", "*.pdf;*.png;*.jpg;*.jpeg;*.webp;*.txt"),
                    ("PDF Documents (*.pdf)", "*.pdf"),
                    ("Slide Images (*.png;*.jpg;*.jpeg;*.webp)", "*.png;*.jpg;*.jpeg;*.webp"),
                    ("Plain Text Notes (*.txt)", "*.txt"),
                    ("All Files (*.*)", "*.*")
                ]
            )
            root.destroy()
            if filepath:
                fname = os.path.basename(filepath)
                with open(filepath, "rb") as f:
                    file_bytes = f.read()
                await self._upload_and_apply_file(fname, file_bytes)
        except Exception:
            pass

    async def _upload_and_apply_file(self, name: str, file_bytes: bytes):
        """Uploads file to backend /api/upload and performs security validation."""
        self.file_status_text.value = f"Verifying & securing '{name}'..."
        self.file_status_text.color = TEXT_MUTED
        self.file_status_text.visible = True
        self.page.update()

        success, msg, data = await api_client.upload_file(name, file_bytes, token=self.token)
        if success and data:
            self.selected_file_name = data.get("original_filename", name)
            self.selected_file_size = data.get("file_size_formatted", "")
            self.uploaded_file_id = data.get("file_id")
            self.file_status_text.value = f"✓ Verified & Stored: {self.selected_file_name} ({self.selected_file_size})"
            self.file_status_text.color = PRIMARY_TEAL
            self.file_status_text.visible = True
            
            # Increment user upload count dynamically
            self.user["total_uploads"] = self.user.get("total_uploads", 0) + 1
            self._update_stats_ui()
            self._notify(msg, is_info=True)
        else:
            self.selected_file_name = None
            self.selected_file_size = None
            self.uploaded_file_id = None
            self.file_status_text.value = f"⚠ Rejected: {msg}"
            self.file_status_text.color = ACCENT_ORANGE_DARK
            self.file_status_text.visible = True
            self._notify(f"Security Alert: {msg}", is_info=False)
        self.page.update()

    async def _handle_upload_pasted_text(self, _):
        """Uploads text typed or pasted in notes_paste_input as a .txt document."""
        text = self.notes_paste_input.value.strip() if self.notes_paste_input.value else ""
        if not text:
            self._notify("Please paste some lecture notes or summary text first.", is_info=False)
            return

        topic = self.topic_input.value.strip() if self.topic_input.value else "lecture_notes"
        safe_topic = re.sub(r"[^a-zA-Z0-9_-]", "_", topic)[:30] or "lecture_notes"
        filename = f"{safe_topic}.txt"
        file_bytes = text.encode("utf-8")
        await self._upload_and_apply_file(filename, file_bytes)

    # ── AI Generation Pipeline ──────────────────────────────────
    async def _handle_generate_session(self, _):
        """Calls Gemini AI backend to generate 30-min study guide & 5-min practice quiz."""
        if self.is_generating:
            return

        notes_content = None
        if self.upload_type == "text":
            notes_content = self.notes_paste_input.value.strip() if self.notes_paste_input.value else ""
            if not notes_content:
                self._notify("Please paste your lecture notes before generating.", is_info=False)
                return
        else:
            if not self.uploaded_file_id:
                self._notify("Please attach and verify a lecture file first.", is_info=False)
                return

        topic = self.topic_input.value.strip() if self.topic_input.value else None

        # Check daily quota limit (3/day for free users, unlimited for Pro)
        user_plan = self.user.get("plan", "free")
        requests_today = self.user.get("requests_today", 0)
        if user_plan == "free" and requests_today >= 3:
            self._notify("Daily free quota reached (3/3). Upgrade to StudyBuddy Pro for unlimited sessions & quizzes!", is_info=False)
            self._show_pro_modal()
            return

        # 1. Update button to loading state
        self.is_generating = True
        orig_btn_content = self.generate_session_btn.content
        self.generate_session_btn.content = ft.Row([
            ft.ProgressRing(width=16, height=16, stroke_width=2.5, color=ft.Colors.WHITE),
            ft.Text("Analyzing with Gemini 3.5 Flash... (~15s)", color=ft.Colors.WHITE, size=13, weight=ft.FontWeight.BOLD),
        ], alignment=ft.MainAxisAlignment.CENTER, spacing=10)
        self.generate_session_btn.bgcolor = PRIMARY_TEAL_DARK
        self.page.update()

        # 2. Call backend /api/ai/generate
        success, msg, data = await api_client.generate_study_session(
            file_id=self.uploaded_file_id if self.upload_type == "file" else None,
            notes_text=notes_content if self.upload_type == "text" else None,
            topic=topic,
            mode=self.selected_mode,
            quiz_question_count=self.selected_quiz_count,
            token=self.token,
        )

        # 3. Restore button state
        self.is_generating = False
        self.generate_session_btn.content = orig_btn_content
        self.generate_session_btn.bgcolor = PRIMARY_TEAL
        self.page.update()

        if not success or not data:
            self._notify(f"Generation Failed: {msg}", is_info=False)
            return

        # 4. Save generated pack & award user XP
        self.current_session = data
        self.history_items.insert(0, data)
        self.user["xp"] = self.user.get("xp", 0) + 50
        self.user["requests_today"] = self.user.get("requests_today", 0) + 1
        self._update_stats_ui()
        self._notify("⚡ 30-Minute Study Session ready! (+50 XP Earned)", is_info=True)

        # 5. Route to appropriate view based on mode
        if self.selected_mode == "quiz":
            await self._start_quiz_session()
        else:
            self._show_summary_view()

    # ── View Switchers (Stay on Dashboard) ───────────────────────
    def _show_workspace_view(self):
        """Switches center card back to the Upload & Config Workspace."""
        self._stop_quiz_timer()
        self.center_mode = "workspace"
        self.active_nav = "Workspace"
        self._update_nav_styles()
        self.center_card_container.content = self._build_center_workspace_card()
        self.page.update()
        try:
            if not self.history_items:
                asyncio.create_task(self._fetch_history_from_backend())
        except RuntimeError:
            pass

    def _show_history_view(self):
        """Switches center card to display the persistent Study History section."""
        self._stop_quiz_timer()
        self.center_mode = "history"
        self.active_nav = "History"
        self._update_nav_styles()
        self.center_card_container.content = self._build_history_card()
        self.page.update()
        try:
            asyncio.create_task(self._fetch_history_from_backend())
        except RuntimeError:
            pass

    def _show_achievements_view(self):
        """Switches center card to display the Achievements & Scholar Progression section."""
        self._stop_quiz_timer()
        self.center_mode = "achievements"
        self.active_nav = "Achievements"
        self._update_nav_styles()
        self.center_card_container.content = self._build_achievements_card()
        self.page.update()
        try:
            asyncio.create_task(self._refresh_user_profile())
        except RuntimeError:
            pass

    def _show_profile_view(self):
        """Switches center card to display the Student Profile & Subject Skill Radar view."""
        self._stop_quiz_timer()
        self.center_mode = "profile"
        self.active_nav = "Profile"
        self._update_nav_styles()
        self.center_card_container.content = self._build_profile_card()
        self.page.update()
        try:
            asyncio.create_task(self._refresh_user_profile())
            if not self.history_items:
                asyncio.create_task(self._fetch_history_from_backend())
        except RuntimeError:
            pass

    def _show_summary_view(self):
        """Switches center card to display the 30-minute exam summary."""
        self._stop_quiz_timer()
        self.center_mode = "summary"
        self.center_card_container.content = self._build_summary_card()
        self.page.update()

    async def _start_quiz_session(self):
        """Initializes and displays the timed practice quiz."""
        if not self.current_session or not self.current_session.get("quiz"):
            self._notify("No quiz questions available for this study session.", is_info=False)
            return

        quiz_list = self.current_session.get("quiz", [])
        total_q = len(quiz_list)
        self.center_mode = "quiz"
        self.quiz_current_index = 0
        self.quiz_selected_answers = {}
        # Dynamic timer: 1 minute per question, minimum 3 minutes (180s)
        self.quiz_total_timer_seconds = max(180, total_q * 60)
        self.quiz_timer_seconds = self.quiz_total_timer_seconds
        self.quiz_timer_running = True
        self.center_card_container.content = self._build_quiz_card()
        self.page.update()

        # Start background countdown loop
        if self.quiz_timer_task and not self.quiz_timer_task.done():
            self.quiz_timer_task.cancel()
        self.quiz_timer_task = asyncio.create_task(self._run_quiz_timer())

    def _stop_quiz_timer(self):
        self.quiz_timer_running = False
        if self.quiz_timer_task and not self.quiz_timer_task.done():
            self.quiz_timer_task.cancel()

    async def _run_quiz_timer(self):
        """Background countdown loop updating the timer bar and text."""
        try:
            while self.quiz_timer_running and self.quiz_timer_seconds > 0:
                await asyncio.sleep(1)
                if not self.quiz_timer_running:
                    break
                self.quiz_timer_seconds -= 1
                if self.center_mode == "quiz":
                    self._update_quiz_timer_ui()

            if self.quiz_timer_running and self.quiz_timer_seconds <= 0:
                self.quiz_timer_running = False
                self._notify("⏱ Time is up! Submitting quiz automatically...", is_info=False)
                await self._submit_quiz()
        except asyncio.CancelledError:
            pass

    def _update_quiz_timer_ui(self):
        """Refreshes the countdown text and progress bar during active quiz."""
        mins = self.quiz_timer_seconds // 60
        secs = self.quiz_timer_seconds % 60
        time_str = f"{mins:02d}:{secs:02d}"
        total_time = float(getattr(self, "quiz_total_timer_seconds", 300) or 300)
        pct = max(0.0, min(1.0, self.quiz_timer_seconds / total_time))

        if hasattr(self, "quiz_timer_text") and self.quiz_timer_text:
            self.quiz_timer_text.value = f"⏱ {time_str}"
            self.quiz_timer_text.color = ACCENT_ORANGE_DARK if self.quiz_timer_seconds < 60 else PRIMARY_TEAL
        if hasattr(self, "quiz_progress_bar") and self.quiz_progress_bar:
            self.quiz_progress_bar.value = pct
            self.quiz_progress_bar.color = ACCENT_ORANGE_DARK if self.quiz_timer_seconds < 60 else PRIMARY_TEAL
        self.page.update()

    async def _submit_quiz(self):
        """Submits student quiz answers, fetches scores, and shows review."""
        self._stop_quiz_timer()
        if not self.current_session:
            return

        session_id = self.current_session.get("session_id")
        quiz_list = self.current_session.get("quiz", [])
        answers_payload = [
            {"question_index": i, "selected_option_index": self.quiz_selected_answers.get(i, -1)}
            for i in range(len(quiz_list))
        ]
        time_taken = max(1, getattr(self, "quiz_total_timer_seconds", 300) - self.quiz_timer_seconds)

        success, msg, result = await api_client.submit_quiz(
            session_id=session_id,
            answers=answers_payload,
            time_taken_seconds=time_taken,
            token=self.token,
        )

        if success and result:
            self.quiz_results = result
            # Update user stats dynamically
            self.user["xp"] = self.user.get("xp", 0) + result.get("xp_earned", 0)
            score_pct = result.get("score_percent", 0.0)
            old_best = float(self.user.get("best_quiz_score", 0.0))
            self.user["best_quiz_score"] = max(old_best, score_pct)
            self._update_stats_ui()

            # Render review
            self.center_mode = "review"
            self.center_card_container.content = self._build_quiz_review_card()
            self._notify(result.get("message", "Quiz completed!"), is_info=True)
        else:
            self._notify(f"Quiz scoring error: {msg}", is_info=False)
        self.page.update()

    def _update_stats_ui(self):
        """Updates navbar pills, left history card, and right achievements card in real-time."""
        streak_val = self.user.get("streak", 0)
        xp_val = self.user.get("xp", 0)
        level_val = 1 + (xp_val // 200)
        self.user["level"] = level_val
        requests_today = self.user.get("requests_today", 0)
        requests_left = max(0, 3 - requests_today)
        is_pro = (self.user.get("plan", "free") == "pro")

        if self.streak_pill_text:
            self.streak_pill_text.value = f"{streak_val}d"
        if self.xp_pill_text:
            self.xp_pill_text.value = f"Lv.{level_val} • {xp_val} XP"
        if self.quota_pill_text:
            self.quota_pill_text.value = "Pro • Unlimited" if is_pro else f"{requests_left}/3 Free"
            self.quota_pill_text.color = PRIMARY_TEAL if is_pro else TEXT_TITLE

        if hasattr(self, "nav_pro_btn") and self.nav_pro_btn:
            self.nav_pro_btn.bgcolor = PRIMARY_TEAL if is_pro else ACCENT_ORANGE
            if hasattr(self, "nav_pro_text") and self.nav_pro_text:
                self.nav_pro_text.value = "Pro Active" if is_pro else "Pro Upgrade"

        # Re-render sidebars
        self.left_history_container.content = self._build_left_history_card_content()
        self.right_achievements_container.content = self._build_right_achievements_card_content()
        if self.center_mode == "achievements":
            self.center_card_container.content = self._build_achievements_card()
        elif self.center_mode == "profile":
            self.center_card_container.content = self._build_profile_card()
        self.page.update()

    # ── UI Interactive State Handlers ───────────────────────────
    def _select_mode(self, mode: str):
        self.selected_mode = mode
        for card, card_mode in [
            (self.mode_summary_card, "summary"),
            (self.mode_quiz_card, "quiz"),
            (self.mode_both_card, "both")
        ]:
            if card_mode == mode:
                card.bgcolor = PRIMARY_TEAL_LIGHT
                card.border = ft.Border.all(1.5, PRIMARY_TEAL)
            else:
                card.bgcolor = CARD_BG
                card.border = ft.Border.all(1, BORDER_COLOR)

        if hasattr(self, "quiz_count_section") and self.quiz_count_section:
            self.quiz_count_section.visible = (mode in ("quiz", "both"))

        q_count = getattr(self, "selected_quiz_count", 5)
        if mode == "both":
            self.mode_subtext.value = f"Displays the 30-min summary first, then seamlessly unlocks the {q_count}-question practice quiz."
            self._notify(f"Selected Exam Prep Mode: Summary + {q_count}-Q Practice Quiz")
        elif mode == "summary":
            self.mode_subtext.value = "Generates high-yield bullet point breakdowns, core formulas, and key definitions."
            self._notify("Selected Exam Prep Mode: Summary Only")
        elif mode == "quiz":
            self.mode_subtext.value = f"Generates a timed practice quiz with {q_count} questions to test recall."
            self._notify(f"Selected Exam Prep Mode: Quiz Only ({q_count} Qs)")

        self._update_generate_btn_label()
        self.page.update()

    def _select_quiz_count(self, count: int):
        self.selected_quiz_count = count
        if hasattr(self, "quiz_count_chips") and self.quiz_count_chips:
            for c_val, c_container in self.quiz_count_chips.items():
                is_active = (c_val == count)
                c_container.bgcolor = PRIMARY_TEAL_LIGHT if is_active else CARD_BG
                c_container.border = ft.Border.all(1.5 if is_active else 1, PRIMARY_TEAL if is_active else BORDER_COLOR)
                if hasattr(c_container.content, "controls"):
                    c_container.content.controls[0].color = PRIMARY_TEAL_DARK if is_active else TEXT_BODY
                    c_container.content.controls[0].weight = ft.FontWeight.BOLD if is_active else ft.FontWeight.W_600
                    c_container.content.controls[1].color = PRIMARY_TEAL_DARK if is_active else TEXT_MUTED

        if self.selected_mode == "both":
            self.mode_subtext.value = f"Displays the 30-min summary first, then seamlessly unlocks the {count}-question practice quiz."
        elif self.selected_mode == "quiz":
            self.mode_subtext.value = f"Generates a timed practice quiz with {count} questions to test recall."

        self._update_generate_btn_label()
        self._notify(f"Selected Quiz Length: {count} questions")
        self.page.update()

    def _update_generate_btn_label(self):
        if not hasattr(self, "generate_btn_text") or not self.generate_btn_text:
            return
        q_count = getattr(self, "selected_quiz_count", 5)
        if self.selected_mode == "summary":
            self.generate_btn_text.value = "Generate 30-Minute Study Guide"
        elif self.selected_mode == "quiz":
            self.generate_btn_text.value = f"Generate {q_count}-Question Practice Quiz"
        else: # both
            self.generate_btn_text.value = f"Generate Study Guide + {q_count}-Q Quiz"

    def _select_upload_type(self, upload_type: str):
        self.upload_type = upload_type
        if upload_type == "file":
            self.upload_doc_btn.bgcolor = PRIMARY_TEAL_LIGHT
            self.upload_doc_btn.border = ft.Border.all(1.5, PRIMARY_TEAL)
            self.upload_paste_btn.bgcolor = CARD_BG
            self.upload_paste_btn.border = ft.Border.all(1, BORDER_COLOR)

            self.dropzone_container.visible = True
            self.notes_paste_input.visible = False
            self.notes_word_count.visible = False
            if self.paste_upload_btn:
                self.paste_upload_btn.visible = False
            self._notify("Switched to File Upload mode (PDF, JPG, PNG)")
        else:
            self.upload_paste_btn.bgcolor = PRIMARY_TEAL_LIGHT
            self.upload_paste_btn.border = ft.Border.all(1.5, PRIMARY_TEAL)
            self.upload_doc_btn.bgcolor = CARD_BG
            self.upload_doc_btn.border = ft.Border.all(1, BORDER_COLOR)

            self.dropzone_container.visible = False
            self.notes_paste_input.visible = True
            self.notes_word_count.visible = True
            if self.paste_upload_btn:
                self.paste_upload_btn.visible = True
            self._notify("Switched to Paste Notes mode")
        self.page.update()

    def _apply_quick_topic(self, topic: str):
        self.topic_input.value = topic
        self._notify(f"Applied Quick Test topic: {topic}")
        self.page.update()

    def _on_notes_changed(self, e):
        text = self.notes_paste_input.value or ""
        words = len(text.split()) if text.strip() else 0
        chars = len(text)
        self.notes_word_count.value = f"{words} words • {chars} characters"
        self.page.update()

    def _update_nav_styles(self):
        if not hasattr(self, "nav_workspace_btn") or not self.nav_workspace_btn:
            return
        is_workspace = (self.active_nav == "Workspace")
        is_history = (self.active_nav == "History")
        is_achievements = (self.active_nav == "Achievements")
        is_profile = (self.active_nav == "Profile")

        self.nav_workspace_btn.bgcolor = PRIMARY_TEAL_LIGHT if is_workspace else CARD_BG
        self.nav_workspace_btn.border = ft.Border.all(1, PRIMARY_TEAL if is_workspace else BORDER_COLOR)
        if hasattr(self, "nav_workspace_icon") and self.nav_workspace_icon:
            self.nav_workspace_icon.color = PRIMARY_TEAL if is_workspace else TEXT_MUTED
        if hasattr(self, "nav_workspace_text") and self.nav_workspace_text:
            self.nav_workspace_text.color = PRIMARY_TEAL if is_workspace else TEXT_MUTED
            self.nav_workspace_text.weight = ft.FontWeight.BOLD if is_workspace else ft.FontWeight.W_600

        self.nav_history_btn.bgcolor = PRIMARY_TEAL_LIGHT if is_history else CARD_BG
        self.nav_history_btn.border = ft.Border.all(1, PRIMARY_TEAL if is_history else BORDER_COLOR)
        if hasattr(self, "nav_history_icon") and self.nav_history_icon:
            self.nav_history_icon.color = PRIMARY_TEAL if is_history else TEXT_MUTED
        if hasattr(self, "nav_history_text") and self.nav_history_text:
            self.nav_history_text.color = PRIMARY_TEAL if is_history else TEXT_MUTED
            self.nav_history_text.weight = ft.FontWeight.BOLD if is_history else ft.FontWeight.W_600

        if hasattr(self, "nav_achievements_btn") and self.nav_achievements_btn:
            self.nav_achievements_btn.bgcolor = PRIMARY_TEAL_LIGHT if is_achievements else CARD_BG
            self.nav_achievements_btn.border = ft.Border.all(1, PRIMARY_TEAL if is_achievements else BORDER_COLOR)
        if hasattr(self, "nav_achievements_icon") and self.nav_achievements_icon:
            self.nav_achievements_icon.color = PRIMARY_TEAL if is_achievements else TEXT_MUTED
        if hasattr(self, "nav_achievements_text") and self.nav_achievements_text:
            self.nav_achievements_text.color = PRIMARY_TEAL if is_achievements else TEXT_MUTED
            self.nav_achievements_text.weight = ft.FontWeight.BOLD if is_achievements else ft.FontWeight.W_600

        if hasattr(self, "nav_profile_btn") and self.nav_profile_btn:
            self.nav_profile_btn.bgcolor = PRIMARY_TEAL_LIGHT if is_profile else CARD_BG
            self.nav_profile_btn.border = ft.Border.all(1, PRIMARY_TEAL if is_profile else BORDER_COLOR)
        if hasattr(self, "nav_profile_icon") and self.nav_profile_icon:
            self.nav_profile_icon.color = PRIMARY_TEAL if is_profile else TEXT_MUTED
        if hasattr(self, "nav_profile_text") and self.nav_profile_text:
            self.nav_profile_text.color = PRIMARY_TEAL if is_profile else TEXT_MUTED
            self.nav_profile_text.weight = ft.FontWeight.BOLD if is_profile else ft.FontWeight.W_600

    async def _fetch_history_from_backend(self, notify_user: bool = False):
        """Fetches the user's persistent study history from MongoDB backend."""
        if not self.token:
            return
        success, msg, items = await api_client.get_history(self.token)
        if success and items is not None:
            self.history_items = items
            self.left_history_container.content = self._build_left_history_card_content()
            if self.center_mode == "history":
                self.center_card_container.content = self._build_history_card()
            try:
                self.page.update()
            except Exception:
                pass
            if notify_user:
                self._notify(f"History refreshed: {len(items)} session(s) loaded.", is_info=True)
        elif notify_user:
            self._notify(f"Could not refresh history: {msg}", is_info=False)

    async def _refresh_user_profile(self, notify_user: bool = False):
        """Syncs current user profile (XP, level, badges, streak, best score) from backend."""
        if not self.token:
            return
        success, msg, profile = await api_client.get_me(self.token)
        if success and profile:
            self.user = profile
            self._update_stats_ui()
            if notify_user:
                self._notify("Scholar stats and achievements synchronized!", is_info=True)
        elif notify_user:
            self._notify(f"Could not sync achievements: {msg}", is_info=False)

    def _on_nav_clicked(self, nav_name: str):
        self.active_nav = nav_name
        self._update_nav_styles()
        if nav_name == "Workspace":
            self._show_workspace_view()
            self._notify("Active Workspace: StudyBuddy Prep Dashboard")
        elif nav_name == "History":
            self._show_history_view()
            self._notify("Active View: Study History", is_info=True)
        elif nav_name == "Achievements":
            self._show_achievements_view()
            self._notify("Active View: Achievements & Scholar Progression", is_info=True)
        elif nav_name == "Profile":
            self._show_profile_view()
            self._notify("Active View: Scholar Profile & Subject Skills", is_info=True)
        elif nav_name == "Pro Upgrade":
            self._show_pro_modal()

    def _show_pro_modal(self):
        """Displays Pro Upgrade checkout modal with dynamic XP discount and SSLCommerz Sandbox integration."""
        def close_dialog(_=None):
            dialog.open = False
            self.page.update()

        user_xp = self.user.get("xp", 0)
        is_pro = self.user.get("plan", "free") == "pro"
        base_price = 499.0
        has_discount = (user_xp > 250)
        discount_amount = round(base_price * 0.05, 2) if has_discount else 0.0
        final_price = round(base_price - discount_amount, 2)

        if is_pro:
            # Active Pro member confirmation dialog
            dialog = ft.AlertDialog(
                title=ft.Row([
                    ft.Icon(ft.Icons.WORKSPACE_PREMIUM_ROUNDED, color=PRIMARY_TEAL, size=24),
                    ft.Text("StudyBuddy Pro Active", size=18, weight=ft.FontWeight.BOLD, color=TEXT_TITLE),
                ], spacing=8),
                content=ft.Column([
                    ft.Container(
                        content=ft.Column([
                            ft.Row([
                                ft.Icon(ft.Icons.CHECK_CIRCLE, color=PRIMARY_TEAL, size=20),
                                ft.Text("Unlimited Study Packs & Daily Sessions", size=13, weight=ft.FontWeight.W_600, color=TEXT_TITLE),
                            ], spacing=8),
                            ft.Row([
                                ft.Icon(ft.Icons.CHECK_CIRCLE, color=PRIMARY_TEAL, size=20),
                                ft.Text("Unlimited Practice Quiz Generation", size=13, weight=ft.FontWeight.W_600, color=TEXT_TITLE),
                            ], spacing=8),
                            ft.Row([
                                ft.Icon(ft.Icons.CHECK_CIRCLE, color=PRIMARY_TEAL, size=20),
                                ft.Text("Priority AI Processing & Explanations", size=13, weight=ft.FontWeight.W_600, color=TEXT_TITLE),
                            ], spacing=8),
                            ft.Row([
                                ft.Icon(ft.Icons.CHECK_CIRCLE, color=PRIMARY_TEAL, size=20),
                                ft.Text("Verified Pro Scholar Status", size=13, weight=ft.FontWeight.W_600, color=TEXT_TITLE),
                            ], spacing=8),
                        ], spacing=10),
                        padding=16,
                        bgcolor=PRIMARY_TEAL_LIGHT,
                        border_radius=12,
                        border=ft.Border.all(1, PRIMARY_TEAL_BORDER),
                    ),
                    ft.Text("Your account has lifetime Pro privileges unlocked in this session.", size=12, color=TEXT_MUTED),
                ], tight=True, spacing=14),
                actions=[
                    ft.FilledButton("Close", bgcolor=PRIMARY_TEAL, color=ft.Colors.WHITE, on_click=close_dialog),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            self.page.overlay.append(dialog)
            dialog.open = True
            self.page.update()
            return

        # Free tier: render Upgrade modal with XP discount & SSLCommerz Sandbox
        if has_discount:
            pricing_box = ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Container(
                            content=ft.Row([
                                ft.Icon(ft.Icons.DISCOUNT_ROUNDED, size=13, color=PRIMARY_TEAL),
                                ft.Text("5% SCHOLAR XP BONUS ACTIVE", size=10, weight=ft.FontWeight.BOLD, color=PRIMARY_TEAL),
                            ], spacing=4),
                            padding=ft.Padding(8, 3, 8, 3),
                            bgcolor=PRIMARY_TEAL_LIGHT,
                            border_radius=12,
                            border=ft.Border.all(1, PRIMARY_TEAL_BORDER),
                        ),
                        ft.Text(f"XP: {user_xp} (> 250)", size=11, weight=ft.FontWeight.W_600, color=TEXT_MUTED),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ft.Row([
                        ft.Text(f"Regular: ৳{base_price:.2f}", size=13, color=TEXT_LIGHT),
                        ft.Text(f"৳{final_price:.2f}", size=22, weight=ft.FontWeight.BOLD, color=PRIMARY_TEAL),
                        ft.Text("/ month", size=12, color=TEXT_MUTED),
                        ft.Container(
                            content=ft.Text(f"Save ৳{discount_amount:.2f}", size=10, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                            padding=ft.Padding(6, 2, 6, 2),
                            bgcolor="#10B981",
                            border_radius=8,
                        ),
                    ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Text("Congratulations! Because your Scholar XP exceeds 250, an exclusive 5% discount was applied.", size=11, color=TEXT_MUTED),
                ], spacing=6),
                padding=14,
                bgcolor=INSET_BG,
                border_radius=12,
                border=ft.Border.all(1, PRIMARY_TEAL_BORDER),
            )
        else:
            pricing_box = ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Text(f"৳{base_price:.2f}", size=22, weight=ft.FontWeight.BOLD, color=TEXT_TITLE),
                        ft.Text("/ month", size=12, color=TEXT_MUTED),
                    ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Row([
                        ft.Icon(ft.Icons.LIGHTBULB_OUTLINE_ROUNDED, size=13, color=ACCENT_ORANGE),
                        ft.Text(f"Earn >250 XP to unlock 5% student discount (Current: {user_xp}/250 XP).", size=11, color=TEXT_MUTED),
                    ], spacing=4),
                ], spacing=4),
                padding=14,
                bgcolor=INSET_BG,
                border_radius=12,
                border=ft.Border.all(1, BORDER_COLOR),
            )

        features_box = ft.Container(
            content=ft.Column([
                ft.Row([ft.Icon(ft.Icons.CHECK, color=PRIMARY_TEAL, size=16), ft.Text("Unlimited Study Sessions / day (more than 3/day free cap)", size=12, weight=ft.FontWeight.W_500, color=TEXT_BODY)]),
                ft.Row([ft.Icon(ft.Icons.CHECK, color=PRIMARY_TEAL, size=16), ft.Text("Unlimited Practice Quiz Generation", size=12, weight=ft.FontWeight.W_500, color=TEXT_BODY)]),
                ft.Row([ft.Icon(ft.Icons.CHECK, color=PRIMARY_TEAL, size=16), ft.Text("Detailed question mistake analysis and explanations", size=12, weight=ft.FontWeight.W_500, color=TEXT_BODY)]),
                ft.Row([ft.Icon(ft.Icons.CHECK, color=PRIMARY_TEAL, size=16), ft.Text("SSLCommerz Developer Sandbox (bKash, Nagad, Cards)", size=12, weight=ft.FontWeight.W_500, color=TEXT_BODY)]),
            ], spacing=8),
            padding=14,
            bgcolor=CARD_BG_MUTED,
            border_radius=12,
            border=ft.Border.all(1, BORDER_COLOR),
        )

        modal_body = ft.Column([
            pricing_box,
            features_box,
        ], tight=True, spacing=12)

        active_tran_id = [None]

        async def check_payment_status(_=None):
            if not active_tran_id[0] or not self.token:
                return
            success, msg, status_data = await api_client.get_payment_status(self.token, active_tran_id[0])
            if success and status_data:
                st = status_data.get("status")
                if st == "completed" or status_data.get("is_pro"):
                    self.user["plan"] = "pro"
                    self._update_stats_ui()
                    close_dialog()
                    self._notify("🎉 Welcome to StudyBuddy Pro! Unlimited preps and quizzes unlocked.", is_info=True)
                else:
                    self._notify(f"Payment status: {st.capitalize()}. Complete checkout in browser then re-check.", is_info=True)
            else:
                self._notify(f"Status check error: {msg}", is_info=False)

        async def simulate_instant_pay(_=None):
            if not active_tran_id[0] or not self.token:
                return
            success, msg, res = await api_client.simulate_payment_success(self.token, active_tran_id[0])
            if success:
                self.user["plan"] = "pro"
                self._update_stats_ui()
                close_dialog()
                self._notify("🎉 Sandbox Payment Confirmed! StudyBuddy Pro Activated.", is_info=True)
            else:
                self._notify(f"Simulation error: {msg}", is_info=False)

        async def start_checkout(_=None):
            if not self.token:
                self._notify("Please log in to upgrade.", is_info=False)
                return

            pay_button.content = ft.Row([
                ft.ProgressRing(width=14, height=14, stroke_width=2, color=ft.Colors.WHITE),
                ft.Text("Connecting SSLCommerz Sandbox...", size=12, color=ft.Colors.WHITE),
            ], alignment=ft.MainAxisAlignment.CENTER, spacing=8)
            pay_button.disabled = True
            self.page.update()

            success, msg, data = await api_client.initiate_payment(self.token)
            if not success or not data:
                pay_button.disabled = False
                pay_button.content = ft.Text(f"Pay ৳{final_price:.2f} via SSLCommerz Sandbox", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE)
                self.page.update()
                self._notify(f"Payment initialization failed: {msg}", is_info=False)
                return

            gateway_url = data.get("gateway_url")
            tran_id = data.get("transaction_id")
            active_tran_id[0] = tran_id

            import webbrowser
            try:
                webbrowser.open(gateway_url)
            except Exception:
                pass

            modal_body.controls = [
                ft.Container(
                    content=ft.Column([
                        ft.Icon(ft.Icons.PAYMENT_ROUNDED, size=36, color=PRIMARY_TEAL),
                        ft.Text("SSLCommerz Sandbox Checkout Opened", size=15, weight=ft.FontWeight.BOLD, color=TEXT_TITLE),
                        ft.Text("A browser tab has opened with the SSLCommerz test portal.", size=12, color=TEXT_MUTED, text_align=ft.TextAlign.CENTER),
                        ft.Container(
                            content=ft.Text(f"Transaction: {tran_id}", size=11, font_family="monospace", color=PRIMARY_TEAL),
                            padding=ft.Padding(8, 4, 8, 4),
                            bgcolor=PRIMARY_TEAL_LIGHT,
                            border_radius=8,
                        ),
                        ft.Text("Complete payment in browser using test bKash, Nagad, or Cards.", size=11, color=TEXT_MUTED),
                    ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=6),
                    padding=16,
                    bgcolor=CARD_BG_MUTED,
                    border_radius=12,
                    border=ft.Border.all(1, BORDER_COLOR),
                ),
            ]

            dialog.actions = [
                ft.TextButton("Cancel", on_click=close_dialog),
                ft.OutlinedButton(
                    "Check Status",
                    on_click=lambda e: asyncio.create_task(check_payment_status(e)),
                ),
                ft.FilledButton(
                    "⚡ Instant Sandbox Demo Pay",
                    bgcolor=PRIMARY_TEAL,
                    color=ft.Colors.WHITE,
                    on_click=lambda e: asyncio.create_task(simulate_instant_pay(e)),
                ),
            ]
            self.page.update()

        pay_button = ft.FilledButton(
            f"Pay ৳{final_price:.2f} via SSLCommerz Sandbox",
            bgcolor=ACCENT_ORANGE,
            color=ft.Colors.WHITE,
            on_click=lambda e: asyncio.create_task(start_checkout(e)),
        )

        dialog = ft.AlertDialog(
            title=ft.Row([
                ft.Icon(ft.Icons.AUTO_AWESOME, color=ACCENT_ORANGE, size=24),
                ft.Text("StudyBuddy Pro Upgrade", size=18, weight=ft.FontWeight.BOLD, color=TEXT_TITLE),
            ], spacing=8),
            content=ft.Container(content=modal_body, width=420),
            actions=[
                ft.TextButton("Maybe Later", on_click=close_dialog),
                pay_button,
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()

    def _show_user_menu(self):
        """Displays user profile & logout confirmation dialog."""
        def close_dialog(_):
            menu_dialog.open = False
            self.page.update()

        name = self.user.get("name") or "Student"
        email = self.user.get("email") or ""
        plan = (self.user.get("plan") or "free").capitalize()
        streak_val = self.user.get("streak", 0)
        xp_val = self.user.get("xp", 0)
        level_val = self.user.get("level", 1)

        menu_dialog = ft.AlertDialog(
            title=ft.Row([
                ft.CircleAvatar(
                    content=ft.Text(name[0].upper(), color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
                    bgcolor=PRIMARY_TEAL,
                    radius=18,
                ),
                ft.Column([
                    ft.Text(name, size=16, weight=ft.FontWeight.BOLD, color=TEXT_TITLE),
                    ft.Text(email, size=12, color=TEXT_MUTED),
                ], spacing=2),
            ], spacing=10),
            content=ft.Column([
                ft.Row([ft.Text("Plan Tier:", size=13, color=TEXT_MUTED), ft.Text(f"{plan} Plan (3 requests/day)", size=13, weight=ft.FontWeight.BOLD, color=PRIMARY_TEAL)]),
                ft.Row([ft.Text("Current Streak:", size=13, color=TEXT_MUTED), ft.Text(f"{streak_val} Days 🔥", size=13, weight=ft.FontWeight.BOLD, color=ACCENT_ORANGE_DARK)]),
                ft.Row([ft.Text("Total XP:", size=13, color=TEXT_MUTED), ft.Text(f"{xp_val} XP (Level {level_val})", size=13, weight=ft.FontWeight.BOLD, color=TEXT_TITLE)]),
            ], tight=True, spacing=8),
            actions=[
                ft.TextButton(
                    "View Full Profile & Skills",
                    icon=ft.Icons.PERSON_PIN_ROUNDED,
                    on_click=lambda _: (close_dialog(_), self._show_profile_view()),
                ),
                ft.TextButton("Close", on_click=close_dialog),
                ft.FilledButton(
                    "Log Out",
                    bgcolor=ft.Colors.RED_500,
                    color=ft.Colors.WHITE,
                    on_click=lambda _: (close_dialog(_), self.on_logout()),
                ),
            ],
        )
        self.page.overlay.append(menu_dialog)
        menu_dialog.open = True
        self.page.update()

    # ── Navbar Component ─────────────────────────────────────────
    def _build_navbar(self) -> ft.Container:
        user_name = self.user.get("name") or "Student"
        streak_val = self.user.get("streak", 0)
        xp_val = self.user.get("xp", 0)
        level_val = self.user.get("level", 1)
        requests_today = self.user.get("requests_today", 0)
        requests_left = max(0, 3 - requests_today)

        # Brand Logo
        logo_icon = ft.Container(
            content=ft.Icon(ft.Icons.BOLT, color=ft.Colors.WHITE, size=22),
            width=36,
            height=36,
            border_radius=18,
            bgcolor=PRIMARY_TEAL,
            alignment=ft.Alignment(0, 0),
        )

        brand_col = ft.Column([
            ft.Row([
                ft.Text("StudyBuddy", size=18, weight=ft.FontWeight.BOLD, color=TEXT_TITLE),
            ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Text("30-Minute Summary & 5-Minute Timed Quiz", size=10, color=TEXT_MUTED),
        ], spacing=1)

        # Navigation Buttons
        is_workspace = (self.active_nav == "Workspace")
        is_history = (self.active_nav == "History")

        self.nav_workspace_icon = ft.Icon(ft.Icons.DASHBOARD_ROUNDED, size=15, color=PRIMARY_TEAL if is_workspace else TEXT_MUTED)
        self.nav_workspace_text = ft.Text("Workspace", size=12, weight=ft.FontWeight.BOLD if is_workspace else ft.FontWeight.W_600, color=PRIMARY_TEAL if is_workspace else TEXT_TITLE)
        self.nav_workspace_btn = ft.Container(
            content=ft.Row([self.nav_workspace_icon, self.nav_workspace_text], spacing=6),
            padding=ft.Padding(12, 6, 12, 6),
            bgcolor=PRIMARY_TEAL_LIGHT if is_workspace else CARD_BG,
            border_radius=20,
            border=ft.Border.all(1, PRIMARY_TEAL if is_workspace else BORDER_COLOR),
            shadow=SOFT_SHADOW,
            on_click=lambda _: self._on_nav_clicked("Workspace"),
        )

        self.nav_history_icon = ft.Icon(ft.Icons.HISTORY_ROUNDED, size=15, color=PRIMARY_TEAL if is_history else TEXT_MUTED)
        self.nav_history_text = ft.Text("History", size=12, weight=ft.FontWeight.BOLD if is_history else ft.FontWeight.W_600, color=PRIMARY_TEAL if is_history else TEXT_MUTED)
        self.nav_history_btn = ft.Container(
            content=ft.Row([self.nav_history_icon, self.nav_history_text], spacing=6),
            padding=ft.Padding(12, 6, 12, 6),
            bgcolor=PRIMARY_TEAL_LIGHT if is_history else CARD_BG,
            border_radius=20,
            border=ft.Border.all(1, PRIMARY_TEAL if is_history else BORDER_COLOR),
            on_click=lambda _: self._on_nav_clicked("History"),
        )

        is_achievements = (self.active_nav == "Achievements")
        self.nav_achievements_icon = ft.Icon(ft.Icons.EMOJI_EVENTS_OUTLINED, size=15, color=PRIMARY_TEAL if is_achievements else TEXT_MUTED)
        self.nav_achievements_text = ft.Text("Achievements", size=12, weight=ft.FontWeight.BOLD if is_achievements else ft.FontWeight.W_600, color=PRIMARY_TEAL if is_achievements else TEXT_MUTED)
        self.nav_achievements_btn = ft.Container(
            content=ft.Row([
                self.nav_achievements_icon,
                self.nav_achievements_text,
            ], spacing=6),
            padding=ft.Padding(12, 6, 12, 6),
            bgcolor=PRIMARY_TEAL_LIGHT if is_achievements else CARD_BG,
            border_radius=20,
            border=ft.Border.all(1, PRIMARY_TEAL if is_achievements else BORDER_COLOR),
            on_click=lambda _: self._on_nav_clicked("Achievements"),
        )

        is_profile = (self.active_nav == "Profile")
        self.nav_profile_icon = ft.Icon(ft.Icons.PERSON_OUTLINED, size=15, color=PRIMARY_TEAL if is_profile else TEXT_MUTED)
        self.nav_profile_text = ft.Text("Profile", size=12, weight=ft.FontWeight.BOLD if is_profile else ft.FontWeight.W_600, color=PRIMARY_TEAL if is_profile else TEXT_MUTED)
        self.nav_profile_btn = ft.Container(
            content=ft.Row([
                self.nav_profile_icon,
                self.nav_profile_text,
            ], spacing=6),
            padding=ft.Padding(12, 6, 12, 6),
            bgcolor=PRIMARY_TEAL_LIGHT if is_profile else CARD_BG,
            border_radius=20,
            border=ft.Border.all(1, PRIMARY_TEAL if is_profile else BORDER_COLOR),
            on_click=lambda _: self._on_nav_clicked("Profile"),
        )

        is_pro = (self.user.get("plan", "free") == "pro")
        self.nav_pro_text = ft.Text("Pro Active" if is_pro else "Pro Upgrade", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE)
        self.nav_pro_btn = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.WORKSPACE_PREMIUM_ROUNDED if is_pro else ft.Icons.AUTO_AWESOME, size=14, color=ft.Colors.WHITE),
                self.nav_pro_text,
            ], spacing=5),
            padding=ft.Padding(14, 6, 14, 6),
            bgcolor=PRIMARY_TEAL if is_pro else ACCENT_ORANGE,
            border_radius=20,
            shadow=ft.BoxShadow(spread_radius=0, blur_radius=8, color="#3300796B" if is_pro else "#33F59E0B", offset=ft.Offset(0, 2)),
            on_click=lambda _: self._on_nav_clicked("Pro Upgrade"),
        )

        # Right Stat Pills (Reactive)
        self.streak_pill_text = ft.Text(f"{streak_val}d", size=12, weight=ft.FontWeight.BOLD, color=ACCENT_ORANGE_DARK)
        streak_pill = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.LOCAL_FIRE_DEPARTMENT, size=14, color=ACCENT_ORANGE_DARK),
                self.streak_pill_text,
            ], spacing=4),
            padding=ft.Padding(10, 5, 10, 5),
            bgcolor=ACCENT_ORANGE_LIGHT,
            border_radius=20,
            border=ft.Border.all(1, ACCENT_ORANGE_BORDER),
            on_click=lambda _: self._notify(f"Current Login Streak: {self.user.get('streak', 0)} day(s). Complete daily quizzes to build streak!"),
        )

        self.xp_pill_text = ft.Text(f"Lv.{level_val} • {xp_val} XP", size=12, weight=ft.FontWeight.W_600, color=TEXT_TITLE)
        xp_pill = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.EMOJI_EVENTS_OUTLINED, size=14, color="#B45309"),
                self.xp_pill_text,
            ], spacing=4),
            padding=ft.Padding(10, 5, 10, 5),
            bgcolor=CARD_BG,
            border_radius=20,
            border=ft.Border.all(1, BORDER_COLOR),
            on_click=lambda _: self._notify(f"Experience: {self.user.get('xp', 0)} XP earned."),
        )

        self.quota_pill_text = ft.Text("Pro • Unlimited" if is_pro else f"{requests_left}/3 Free", size=12, weight=ft.FontWeight.W_600, color=PRIMARY_TEAL if is_pro else TEXT_TITLE)
        quota_pill = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.AUTO_AWESOME, size=14, color=PRIMARY_TEAL),
                self.quota_pill_text,
            ], spacing=4),
            padding=ft.Padding(10, 5, 10, 5),
            bgcolor=PRIMARY_TEAL_LIGHT if is_pro else CARD_BG,
            border_radius=20,
            border=ft.Border.all(1, PRIMARY_TEAL_BORDER if is_pro else BORDER_COLOR),
            on_click=lambda _: self._notify("StudyBuddy Pro Active: Unlimited study preps and quiz generation." if self.user.get("plan") == "pro" else f"Daily Free Quota: {max(0, 3 - self.user.get('requests_today', 0))} requests remaining today."),
        )

        user_profile_pill = ft.Container(
            content=ft.Row([
                ft.CircleAvatar(
                    content=ft.Text(user_name[0].upper(), size=12, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
                    radius=13,
                    bgcolor=PRIMARY_TEAL,
                ),
                ft.Text(user_name, size=13, weight=ft.FontWeight.W_600, color=TEXT_TITLE),
                ft.Icon(ft.Icons.ARROW_DROP_DOWN, size=16, color=TEXT_MUTED),
            ], spacing=4),
            padding=ft.Padding(8, 4, 10, 4),
            bgcolor=CARD_BG,
            border_radius=20,
            border=ft.Border.all(1, BORDER_COLOR),
            tooltip="User menu & settings",
            on_click=lambda _: self._show_user_menu(),
        )

        logout_pill = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.LOGOUT_ROUNDED, size=14, color=ft.Colors.RED_500),
                ft.Text("Log Out", size=12, weight=ft.FontWeight.W_600, color=ft.Colors.RED_600),
            ], spacing=4),
            padding=ft.Padding(10, 5, 12, 5),
            bgcolor="#FEF2F2",
            border_radius=20,
            border=ft.Border.all(1, "#FECACA"),
            tooltip="Sign out of StudyBuddy",
            on_click=lambda _: self._show_user_menu(),
        )

        return ft.Container(
            content=ft.Row([
                ft.Row([
                    logo_icon,
                    brand_col,
                    ft.Container(width=16),
                    self.nav_workspace_btn,
                    self.nav_history_btn,
                    self.nav_achievements_btn,
                    self.nav_profile_btn,
                    self.nav_pro_btn,
                ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),

                ft.Row([
                    streak_pill,
                    xp_pill,
                    quota_pill,
                    user_profile_pill,
                    logout_pill,
                ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding(20, 12, 20, 12),
        )

    # ── Left Sidebar (Recent History) ───────────────────────────
    def _build_left_history_card_content(self) -> ft.Control:
        sessions_count = len(self.history_items) + self.user.get("total_uploads", 0)

        header = ft.Row([
            ft.Row([
                ft.Container(
                    content=ft.Icon(ft.Icons.HISTORY, size=15, color=PRIMARY_TEAL),
                    width=28,
                    height=28,
                    border_radius=14,
                    bgcolor=PRIMARY_TEAL_LIGHT,
                    alignment=ft.Alignment(0, 0),
                    on_click=lambda _: self._show_history_view(),
                ),
                ft.Column([
                    ft.Text("Recent History", size=13, weight=ft.FontWeight.BOLD, color=TEXT_TITLE),
                    ft.Text(f"{len(self.history_items)} session(s) saved", size=10, color=TEXT_MUTED),
                ], spacing=0),
            ], spacing=8),

            ft.Container(
                content=ft.Icon(ft.Icons.OPEN_IN_NEW_ROUNDED, size=14, color=PRIMARY_TEAL),
                tooltip="Open full History",
                width=24,
                height=24,
                border_radius=12,
                bgcolor=PRIMARY_TEAL_LIGHT,
                alignment=ft.Alignment(0, 0),
                border=ft.Border.all(1, PRIMARY_TEAL_BORDER),
                on_click=lambda _: self._show_history_view(),
            ),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        if not self.history_items:
            empty_illustration = ft.Column([
                ft.Container(
                    content=ft.Icon(ft.Icons.ACCESS_TIME_ROUNDED, size=28, color=TEXT_LIGHT),
                    width=56,
                    height=56,
                    border_radius=28,
                    bgcolor=CARD_BG_MUTED,
                    border=ft.Border.all(1, BORDER_COLOR),
                    alignment=ft.Alignment(0, 0),
                ),
                ft.Text("No sessions yet", size=13, weight=ft.FontWeight.BOLD, color=TEXT_BODY),
                ft.Text(
                    "Upload notes to generate your first study guide!",
                    size=11,
                    color=TEXT_LIGHT,
                    text_align=ft.TextAlign.CENTER,
                ),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=6)

            body_content = ft.Column([
                ft.Container(height=24),
                empty_illustration,
                ft.Container(height=24),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER)
        else:
            # Render list of generated sessions
            session_cards = []
            for item in self.history_items[:5]:
                topic_title = item.get("topic", "Study Session")
                orig_file = item.get("original_filename") or ""
                mode_label = item.get("mode", "both").capitalize()
                
                def _make_loader(rec):
                    return lambda _: self._load_history_item(rec)

                def _make_deleter(rec):
                    return lambda _: self._confirm_delete_history(rec)

                session_cards.append(
                    ft.Container(
                        content=ft.Row([
                            ft.Icon(ft.Icons.BOLT, size=15, color=PRIMARY_TEAL),
                            ft.Column([
                                ft.Text(topic_title[:17] + ("..." if len(topic_title) > 17 else ""), size=11, weight=ft.FontWeight.BOLD, color=TEXT_TITLE),
                                ft.Text(f"{orig_file[:15]}..." if len(orig_file) > 15 else (orig_file or f"{mode_label} • Ready"), size=9, color=TEXT_MUTED),
                            ], spacing=1, expand=True),
                            ft.IconButton(
                                icon=ft.Icons.DELETE_OUTLINE_ROUNDED,
                                icon_size=15,
                                icon_color=TEXT_LIGHT,
                                tooltip="Delete record",
                                on_click=_make_deleter(item),
                            ),
                        ], spacing=2, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        padding=ft.Padding(6, 6, 6, 6),
                        bgcolor=INSET_BG,
                        border_radius=8,
                        border=ft.Border.all(1, BORDER_COLOR),
                        on_click=_make_loader(item),
                    )
                )

            body_content = ft.Column([
                ft.Container(height=10),
                ft.Column(session_cards, spacing=6),
                ft.Container(height=10),
            ])

        action_buttons = []
        if self.history_items:
            view_all_btn = ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.LIST_ALT_ROUNDED, size=13, color=PRIMARY_TEAL),
                    ft.Text(f"View All History ({len(self.history_items)})", size=11, weight=ft.FontWeight.BOLD, color=PRIMARY_TEAL),
                ], spacing=4, alignment=ft.MainAxisAlignment.CENTER),
                padding=ft.Padding(0, 8, 0, 8),
                bgcolor=PRIMARY_TEAL_LIGHT,
                border_radius=16,
                border=ft.Border.all(1, PRIMARY_TEAL_BORDER),
                alignment=ft.Alignment(0, 0),
                on_click=lambda _: self._show_history_view(),
            )
            action_buttons.append(view_all_btn)
            action_buttons.append(ft.Container(height=6))

        history_action_btn = ft.Container(
            content=ft.Text("New Study Session +", size=11, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
            padding=ft.Padding(0, 8, 0, 8),
            bgcolor=PRIMARY_TEAL,
            border_radius=16,
            alignment=ft.Alignment(0, 0),
            on_click=lambda _: self._show_workspace_view(),
        )
        action_buttons.append(history_action_btn)

        content = ft.Column([
            header,
            body_content,
            ft.Column(action_buttons, spacing=0),
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=0)

        return soft_card(content, width=240, padding=16, border_radius=18)

    def _load_history_item(self, item: dict):
        """Loads a past session back into view."""
        self.current_session = item
        if item.get("mode") == "quiz":
            asyncio.create_task(self._start_quiz_session())
        else:
            self._show_summary_view()
        self._notify(f"Loaded: {item.get('topic', 'Study Pack')}")

    def _load_and_start_quiz(self, item: dict):
        """Loads a past session and immediately starts practice quiz."""
        self.current_session = item
        asyncio.create_task(self._start_quiz_session())
        self._notify(f"Starting Quiz: {item.get('topic', 'Practice Quiz')}")

    def _confirm_delete_history(self, item: dict):
        """Displays confirmation dialog before deleting an individual history record."""
        topic = item.get("topic", "this study session")
        h_id = item.get("history_id") or item.get("session_id", "")

        def close_dialog(_):
            dialog.open = False
            self.page.update()

        async def confirm_delete(_):
            dialog.open = False
            self.page.update()
            await self._handle_delete_history(h_id)

        dialog = ft.AlertDialog(
            title=ft.Row([
                ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color=ACCENT_ORANGE_DARK, size=22),
                ft.Text("Delete Study Session?", size=16, weight=ft.FontWeight.BOLD, color=TEXT_TITLE),
            ], spacing=8),
            content=ft.Text(
                f"Are you sure you want to permanently delete the study session for '{topic}'?\nThis will remove it from your history and database.",
                size=12,
                color=TEXT_BODY,
            ),
            actions=[
                ft.TextButton("Cancel", on_click=close_dialog),
                ft.ElevatedButton(
                    "Delete Permanently",
                    bgcolor="#EF4444",
                    color=ft.Colors.WHITE,
                    on_click=lambda e: asyncio.create_task(confirm_delete(e)),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()

    async def _handle_delete_history(self, history_id: str):
        """Deletes a history record from the database and updates frontend state."""
        if not self.token:
            self._notify("Authentication token missing. Please log in again.", is_info=False)
            return

        success, msg = await api_client.delete_history_item(history_id, self.token)
        if success:
            # Remove from local list
            self.history_items = [
                h for h in self.history_items
                if (h.get("history_id") != history_id and h.get("session_id") != history_id)
            ]
            # Clear active session if it was the one deleted
            if self.current_session:
                curr_id = self.current_session.get("history_id") or self.current_session.get("session_id")
                if curr_id == history_id:
                    self.current_session = None

            # Refresh left sidebar
            self.left_history_container.content = self._build_left_history_card_content()

            # Refresh center card
            if self.center_mode == "history":
                self.center_card_container.content = self._build_history_card()
            elif self.center_mode in ("summary", "quiz", "review") and self.current_session is None:
                self._show_workspace_view()

            self.page.update()
            self._notify("Study session permanently removed from history.", is_info=True)
        else:
            self._notify(f"Failed to delete: {msg}", is_info=False)

    # ── Mega Quiz Multi-Session Handlers ─────────────────────────
    def _toggle_mega_quiz_mode(self):
        """Toggles multi-session Mega Quiz selection mode in History view."""
        self.mega_quiz_mode = not self.mega_quiz_mode
        if not self.mega_quiz_mode:
            self.mega_quiz_selected_ids.clear()
            self._notify("Exited Mega Quiz Builder.")
        else:
            self._notify("Mega Quiz Builder active: select sessions below to pool questions.")
        if self.center_mode == "history":
            self.center_card_container.content = self._build_history_card()
            self.page.update()

    def _on_mega_session_toggled(self, session_id: str, is_checked: bool):
        """Adds or removes a session from the selected Mega Quiz pool."""
        if is_checked:
            self.mega_quiz_selected_ids.add(session_id)
        else:
            self.mega_quiz_selected_ids.discard(session_id)
        if self.center_mode == "history":
            self.center_card_container.content = self._build_history_card()
            self.page.update()

    def _mega_quiz_select_all(self, select_all: bool):
        """Selects or clears all eligible past sessions containing quiz questions."""
        if select_all:
            for it in self.history_items:
                q_list = it.get("quiz", [])
                if isinstance(q_list, list) and len(q_list) > 0:
                    sid = it.get("session_id") or it.get("history_id")
                    if sid:
                        self.mega_quiz_selected_ids.add(sid)
            self._notify(f"Selected all {len(self.mega_quiz_selected_ids)} eligible quiz sessions.")
        else:
            self.mega_quiz_selected_ids.clear()
            self._notify("Cleared Mega Quiz selection.")
        if self.center_mode == "history":
            self.center_card_container.content = self._build_history_card()
            self.page.update()

    async def _start_mega_quiz(self):
        """Calls backend /api/ai/quiz/mega to merge selected sessions and launches the exam."""
        if not self.mega_quiz_selected_ids:
            self._notify("Please select at least one study session with quiz questions.", is_info=False)
            return

        session_ids = list(self.mega_quiz_selected_ids)
        self._notify(f"Building pooled Mega Quiz across {len(session_ids)} sessions...", is_info=True)
        success, msg, data = await api_client.create_mega_quiz(session_ids, token=self.token)
        if not success or not data:
            self._notify(f"Could not build Mega Quiz: {msg}", is_info=False)
            return

        self.mega_quiz_mode = False
        self.mega_quiz_selected_ids.clear()
        self.current_session = data
        await self._start_quiz_session()
        total_q = len(data.get("quiz", []))
        self._notify(f"⚡ Mega Quiz Launched: {total_q} Questions ready! Timer scaled.", is_info=True)

    def _stop_quiz_and_exit(self):
        """Stops active quiz timer and safely returns to previous view."""
        self._stop_quiz_timer()
        if self.active_nav == "History":
            self._show_history_view()
        else:
            self._show_workspace_view()
        self._notify("Exited practice quiz.")

    # ── Right Sidebar (Achievements & Gamification) ─────────────
    def _build_right_achievements_card_content(self) -> ft.Control:
        streak_val = self.user.get("streak", 0)
        xp_val = self.user.get("xp", 0)
        level_val = 1 + (xp_val // 200)
        uploads_count = self.user.get("total_uploads", 0)
        best_score = float(self.user.get("best_quiz_score", 0.0))
        best_score_str = f"{int(best_score)}%" if best_score > 0 else "--"

        level_titles = {
            1: "Newcomer",
            2: "Student",
            3: "Learner",
            4: "Scholar",
            5: "Expert",
            6: "Academic Legend"
        }
        level_title = level_titles.get(min(6, level_val), "Scholar")
        progress_val = min(1.0, (xp_val % 200) / 200.0)
        next_level_text = f"{int(progress_val * 100)}% to Lv.{level_val + 1}"

        badges_set = set(self.user.get("badges", []))
        if xp_val >= 50:
            badges_set.add("first")
        if best_score >= 80:
            badges_set.add("quiz")
        if best_score >= 100:
            badges_set.add("legend")
        if uploads_count >= 3:
            badges_set.add("scholar")
        if streak_val >= 3:
            badges_set.add("week")
        if xp_val >= 400:
            badges_set.add("master")
        if xp_val >= 800:
            badges_set.add("prodigy")

        badges_list = sorted(list(badges_set))
        badges_count = len(badges_list)
        badges_pct = int((badges_count / 8.0) * 100)

        header = ft.Container(
            content=ft.Row([
                ft.Row([
                    ft.Container(
                        content=ft.Icon(ft.Icons.EMOJI_EVENTS, size=15, color="#D97706"),
                        width=28,
                        height=28,
                        border_radius=14,
                        bgcolor=ACCENT_ORANGE_LIGHT,
                        alignment=ft.Alignment(0, 0),
                    ),
                    ft.Column([
                        ft.Text("Achievements", size=13, weight=ft.FontWeight.BOLD, color=TEXT_TITLE),
                        ft.Text(f"Level {level_val} • {level_title}", size=10, color=TEXT_MUTED),
                    ], spacing=0),
                ], spacing=8),

                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.LOCAL_FIRE_DEPARTMENT, size=13, color=ACCENT_ORANGE_DARK),
                        ft.Text(f"{streak_val}d Streak", size=10, weight=ft.FontWeight.BOLD, color=ACCENT_ORANGE_DARK),
                    ], spacing=3),
                    padding=ft.Padding(8, 4, 8, 4),
                    bgcolor=ACCENT_ORANGE_LIGHT,
                    border_radius=12,
                    border=ft.Border.all(1, ACCENT_ORANGE_BORDER),
                ),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            on_click=lambda _: self._show_achievements_view(),
            tooltip="Click to view full Achievements and Progression",
        )

        xp_header = ft.Row([
            ft.Row([
                ft.Icon(ft.Icons.BOLT, size=14, color=PRIMARY_TEAL),
                ft.Text("Total Experience", size=12, weight=ft.FontWeight.W_600, color=TEXT_BODY),
            ], spacing=4),
            ft.Text(f"{xp_val} XP", size=13, weight=ft.FontWeight.BOLD, color=TEXT_TITLE),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        progress_bar = ft.ProgressBar(
            value=progress_val,
            color=PRIMARY_TEAL,
            bgcolor="#E2E8F0",
            height=7,
            border_radius=4,
        )

        progress_labels = ft.Row([
            ft.Text(f"Lv.{level_val}", size=10, color=TEXT_MUTED),
            ft.Text(next_level_text, size=10, color=TEXT_MUTED),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        badges_header = ft.Row([
            ft.Text(f"BADGES ({badges_count}/8)", size=10, weight=ft.FontWeight.BOLD, color=TEXT_MUTED),
            ft.Text(f"{badges_pct}% Complete", size=10, weight=ft.FontWeight.BOLD, color=PRIMARY_TEAL),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        badge_meta = {
            "first": ("First", ft.Icons.ROCKET_LAUNCH_ROUNDED),
            "week": ("Streak", ft.Icons.LOCAL_FIRE_DEPARTMENT_ROUNDED),
            "quiz": ("Quiz", ft.Icons.FACT_CHECK_ROUNDED),
            "speed": ("Speed", ft.Icons.BOLT_ROUNDED),
            "scholar": ("Books", ft.Icons.AUTO_STORIES_ROUNDED),
            "legend": ("100%", ft.Icons.WORKSPACE_PREMIUM_ROUNDED),
            "master": ("Honor", ft.Icons.SCHOOL_ROUNDED),
            "prodigy": ("Titan", ft.Icons.DIAMOND_ROUNDED),
        }

        def create_badge_item(slug: str) -> ft.Container:
            name, icon = badge_meta.get(slug, (slug.capitalize(), ft.Icons.MILITARY_TECH))
            unlocked = slug in badges_list
            color = PRIMARY_TEAL if unlocked else TEXT_LIGHT
            bg = PRIMARY_TEAL_LIGHT if unlocked else CARD_BG
            border_c = PRIMARY_TEAL_BORDER if unlocked else BORDER_COLOR
            return ft.Container(
                content=ft.Column([
                    ft.Icon(icon, size=16, color=color),
                    ft.Text(name, size=9, weight=ft.FontWeight.W_600, color=color),
                ], spacing=2, alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                width=46,
                height=46,
                border_radius=10,
                bgcolor=bg,
                border=ft.Border.all(1, border_c),
                alignment=ft.Alignment(0, 0),
                on_click=lambda _: self._show_achievements_view(),
            )

        badges_row_1 = ft.Row([
            create_badge_item("first"),
            create_badge_item("week"),
            create_badge_item("quiz"),
            create_badge_item("speed"),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        badges_row_2 = ft.Row([
            create_badge_item("scholar"),
            create_badge_item("legend"),
            create_badge_item("master"),
            create_badge_item("prodigy"),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        stat_box_1 = ft.Container(
            content=ft.Column([
                ft.Text("Uploads", size=10, color=TEXT_MUTED),
                ft.Text(str(uploads_count), size=16, weight=ft.FontWeight.BOLD, color=TEXT_TITLE),
            ], spacing=2, alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding(12, 8, 12, 8),
            bgcolor=CARD_BG_MUTED,
            border_radius=10,
            border=ft.Border.all(1, BORDER_COLOR),
            expand=True,
        )

        stat_box_2 = ft.Container(
            content=ft.Column([
                ft.Text("Best Score", size=10, color=TEXT_MUTED),
                ft.Text(best_score_str, size=16, weight=ft.FontWeight.BOLD, color=PRIMARY_TEAL),
            ], spacing=2, alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding(12, 8, 12, 8),
            bgcolor=CARD_BG_MUTED,
            border_radius=10,
            border=ft.Border.all(1, BORDER_COLOR),
            expand=True,
        )

        stats_row = ft.Row([stat_box_1, stat_box_2], spacing=8)

        view_achievements_btn = ft.Container(
            content=ft.Text("View Achievements →", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
            padding=ft.Padding(0, 10, 0, 10),
            bgcolor=ACCENT_ORANGE,
            border_radius=20,
            alignment=ft.Alignment(0, 0),
            on_click=lambda _: self._show_achievements_view(),
        )

        content = ft.Column([
            header,
            ft.Divider(height=1, color=BORDER_COLOR),
            xp_header,
            progress_bar,
            progress_labels,
            ft.Container(height=4),
            badges_header,
            badges_row_1,
            badges_row_2,
            ft.Container(height=4),
            stats_row,
            ft.Container(height=8),
            view_achievements_btn,
        ], spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)

        return soft_card(content, width=240, padding=16, border_radius=18)

        content = ft.Column([
            header,
            ft.Divider(height=1, color=BORDER_COLOR),
            xp_header,
            progress_bar,
            progress_labels,
            ft.Container(height=6),
            badges_header,
            badges_row,
            ft.Container(height=6),
            stats_row,
            ft.Container(height=10),
            view_achievements_btn,
        ], spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)

        return soft_card(content, width=240, padding=16, border_radius=18)

    # ── Center: 1. Upload & Workspace Card ───────────────────────
    def _build_center_workspace_card(self) -> ft.Control:
        engine_badge = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.AUTO_AWESOME, size=13, color=PRIMARY_TEAL_DARK),
                ft.Text("Dual AI Engine: 30-Min Summary + 5-Min Timed Quiz", size=11, weight=ft.FontWeight.W_600, color=PRIMARY_TEAL_DARK),
            ], spacing=6, alignment=ft.MainAxisAlignment.CENTER),
            padding=ft.Padding(14, 5, 14, 5),
            bgcolor=PRIMARY_TEAL_LIGHT,
            border_radius=20,
            border=ft.Border.all(1, PRIMARY_TEAL_BORDER),
        )

        title = ft.Text(
            "Turn Lecture Notes into Exam Prep",
            size=24,
            weight=ft.FontWeight.BOLD,
            color=TEXT_TITLE,
            text_align=ft.TextAlign.CENTER,
        )

        subtitle = ft.Text(
            "Upload slides, handwritten lecture photos, or study notes. AI instantly synthesizes core definitions, exam traps, and timed practice questions.",
            size=12,
            color=TEXT_MUTED,
            text_align=ft.TextAlign.CENTER,
        )

        mode_label = ft.Text("CHOOSE YOUR EXAM PREP MODE", size=10, weight=ft.FontWeight.BOLD, color=TEXT_MUTED)

        self.mode_summary_card = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.MENU_BOOK_ROUNDED, size=15, color=PRIMARY_TEAL_DARK),
                ft.Text("Summary Only", size=12, weight=ft.FontWeight.W_600, color=TEXT_BODY),
            ], alignment=ft.MainAxisAlignment.CENTER, spacing=6),
            padding=ft.Padding(12, 10, 12, 10),
            bgcolor=PRIMARY_TEAL_LIGHT if self.selected_mode == "summary" else CARD_BG,
            border_radius=12,
            border=ft.Border.all(1.5 if self.selected_mode == "summary" else 1, PRIMARY_TEAL if self.selected_mode == "summary" else BORDER_COLOR),
            expand=True,
            on_click=lambda _: self._select_mode("summary"),
        )

        self.mode_quiz_card = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.TIMER_OUTLINED, size=15, color=PRIMARY_TEAL_DARK),
                ft.Text("Quiz Only (5m)", size=12, weight=ft.FontWeight.W_600, color=TEXT_BODY),
            ], alignment=ft.MainAxisAlignment.CENTER, spacing=6),
            padding=ft.Padding(12, 10, 12, 10),
            bgcolor=PRIMARY_TEAL_LIGHT if self.selected_mode == "quiz" else CARD_BG,
            border_radius=12,
            border=ft.Border.all(1.5 if self.selected_mode == "quiz" else 1, PRIMARY_TEAL if self.selected_mode == "quiz" else BORDER_COLOR),
            expand=True,
            on_click=lambda _: self._select_mode("quiz"),
        )

        self.mode_both_card = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.LAYERS_ROUNDED, size=15, color=PRIMARY_TEAL_DARK),
                ft.Column([
                    ft.Text("Both", size=12, weight=ft.FontWeight.BOLD, color=TEXT_TITLE),
                    ft.Text("(Recommended)", size=9, weight=ft.FontWeight.W_600, color=PRIMARY_TEAL_DARK),
                ], spacing=0, alignment=ft.MainAxisAlignment.CENTER),
            ], alignment=ft.MainAxisAlignment.CENTER, spacing=6),
            padding=ft.Padding(12, 6, 12, 6),
            bgcolor=PRIMARY_TEAL_LIGHT if self.selected_mode == "both" else CARD_BG,
            border_radius=12,
            border=ft.Border.all(1.5 if self.selected_mode == "both" else 1, PRIMARY_TEAL if self.selected_mode == "both" else BORDER_COLOR),
            expand=True,
            on_click=lambda _: self._select_mode("both"),
        )

        modes_row = ft.Row([
            self.mode_summary_card,
            self.mode_quiz_card,
            self.mode_both_card,
        ], spacing=10)

        # Question count selection chips for practice quizzes
        quiz_count_options = [
            (3, "3 Qs", "Quick Review"),
            (5, "5 Qs", "Standard"),
            (10, "10 Qs", "Deep Practice"),
            (15, "15 Qs", "Mastery Exam"),
        ]
        self.quiz_count_chips = {}
        chips_controls = []
        for count, label_short, label_sub in quiz_count_options:
            is_active = (self.selected_quiz_count == count)
            chip = ft.Container(
                content=ft.Column([
                    ft.Text(label_short, size=12, weight=ft.FontWeight.BOLD if is_active else ft.FontWeight.W_600, color=PRIMARY_TEAL_DARK if is_active else TEXT_BODY),
                    ft.Text(label_sub, size=9, color=PRIMARY_TEAL_DARK if is_active else TEXT_MUTED),
                ], spacing=1, alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.Padding(10, 6, 10, 6),
                bgcolor=PRIMARY_TEAL_LIGHT if is_active else CARD_BG,
                border_radius=10,
                border=ft.Border.all(1.5 if is_active else 1, PRIMARY_TEAL if is_active else BORDER_COLOR),
                expand=True,
                alignment=ft.Alignment(0, 0),
                on_click=lambda _, c=count: self._select_quiz_count(c),
            )
            self.quiz_count_chips[count] = chip
            chips_controls.append(chip)

        self.quiz_count_section = ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.FORMAT_LIST_NUMBERED_ROUNDED, size=13, color=TEXT_MUTED),
                ft.Text("PRACTICE QUIZ LENGTH", size=10, weight=ft.FontWeight.BOLD, color=TEXT_MUTED),
            ], spacing=5),
            ft.Row(chips_controls, spacing=8),
        ], spacing=6, visible=(self.selected_mode in ("quiz", "both")))

        self.upload_doc_btn = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.CLOUD_UPLOAD_OUTLINED, size=14, color=PRIMARY_TEAL_DARK if self.upload_type == "file" else TEXT_MUTED),
                ft.Text("Upload Document / Image", size=12, weight=ft.FontWeight.W_600, color=TEXT_BODY if self.upload_type == "file" else TEXT_MUTED),
            ], spacing=6),
            padding=ft.Padding(12, 6, 12, 6),
            bgcolor=PRIMARY_TEAL_LIGHT if self.upload_type == "file" else CARD_BG,
            border_radius=20,
            border=ft.Border.all(1.5 if self.upload_type == "file" else 1, PRIMARY_TEAL if self.upload_type == "file" else BORDER_COLOR),
            on_click=lambda _: self._select_upload_type("file"),
        )

        self.upload_paste_btn = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.NOTE_ADD_OUTLINED, size=14, color=PRIMARY_TEAL_DARK if self.upload_type == "text" else TEXT_MUTED),
                ft.Text("Paste Notes / Text", size=12, weight=ft.FontWeight.W_600, color=TEXT_BODY if self.upload_type == "text" else TEXT_MUTED),
            ], spacing=6),
            padding=ft.Padding(12, 6, 12, 6),
            bgcolor=PRIMARY_TEAL_LIGHT if self.upload_type == "text" else CARD_BG,
            border_radius=20,
            border=ft.Border.all(1.5 if self.upload_type == "text" else 1, PRIMARY_TEAL if self.upload_type == "text" else BORDER_COLOR),
            on_click=lambda _: self._select_upload_type("text"),
        )

        upload_type_row = ft.Row([
            self.upload_doc_btn,
            self.upload_paste_btn,
        ], spacing=8)

        quick_chips_row = ft.Row([
            ft.Text("Quick Test:", size=11, weight=ft.FontWeight.BOLD, color=TEXT_MUTED),
            ft.Container(
                content=ft.Text("Biology 101", size=11, color=TEXT_BODY),
                padding=ft.Padding(10, 4, 10, 4),
                bgcolor=INSET_BG,
                border_radius=14,
                border=ft.Border.all(1, BORDER_COLOR),
                on_click=lambda _: self._apply_quick_topic("Biology 101: Cellular Respiration & ATP Cycle"),
            ),
            ft.Container(
                content=ft.Text("Computer Science", size=11, color=TEXT_BODY),
                padding=ft.Padding(10, 4, 10, 4),
                bgcolor=INSET_BG,
                border_radius=14,
                border=ft.Border.all(1, BORDER_COLOR),
                on_click=lambda _: self._apply_quick_topic("Computer Science: Big-O Notation & Data Structures"),
            ),
            ft.Container(
                content=ft.Text("General Chemistry", size=11, color=TEXT_BODY),
                padding=ft.Padding(10, 4, 10, 4),
                bgcolor=INSET_BG,
                border_radius=14,
                border=ft.Border.all(1, BORDER_COLOR),
                on_click=lambda _: self._apply_quick_topic("General Chemistry: Thermodynamics & Enthalpy"),
            ),
        ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER)

        subject_label = ft.Text("Subject or Exam Topic (Optional)", size=11, weight=ft.FontWeight.W_600, color=TEXT_MUTED)

        browse_btn = ft.Container(
            content=ft.Text("Browse Files", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
            padding=ft.Padding(20, 8, 20, 8),
            bgcolor=PRIMARY_TEAL,
            border_radius=20,
            on_click=self._handle_browse_click,
        )

        dropzone_content = ft.Column([
            ft.Container(
                content=ft.Icon(ft.Icons.CLOUD_UPLOAD_OUTLINED, size=24, color=PRIMARY_TEAL),
                width=48,
                height=48,
                border_radius=24,
                bgcolor=CARD_BG,
                border=ft.Border.all(1, BORDER_COLOR),
                alignment=ft.Alignment(0, 0),
            ),
            ft.Text("Drag and drop lecture slides, PDF, or note photo", size=13, weight=ft.FontWeight.BOLD, color=TEXT_TITLE),
            ft.Text("Supports PDF, PNG, JPG (including handwritten notes), or TXT up to 50MB", size=11, color=TEXT_LIGHT),
            self.file_status_text,
            browse_btn,
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=6)

        self.dropzone_container = ft.Container(
            content=dropzone_content,
            padding=20,
            bgcolor=CARD_BG_MUTED,
            border_radius=16,
            border=ft.Border.all(1.5, BORDER_COLOR),
            alignment=ft.Alignment(0, 0),
            on_click=self._handle_browse_click,
        )

        self.paste_upload_btn = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.UPLOAD_FILE_OUTLINED, color=PRIMARY_TEAL, size=16),
                ft.Text("Upload & Secure Pasted Notes", color=PRIMARY_TEAL, size=12, weight=ft.FontWeight.BOLD),
            ], alignment=ft.MainAxisAlignment.CENTER, spacing=6),
            bgcolor=PRIMARY_TEAL_LIGHT,
            border=ft.Border.all(1.5, PRIMARY_TEAL),
            padding=ft.Padding(14, 10, 14, 10),
            border_radius=10,
            visible=False,
            on_click=self._handle_upload_pasted_text,
        )

        self.generate_btn_text = ft.Text("Generate 30-Minute Study Guide", color=ft.Colors.WHITE, size=13, weight=ft.FontWeight.BOLD)
        self._update_generate_btn_label()

        self.generate_session_btn = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.BOLT, color=ft.Colors.WHITE, size=18),
                self.generate_btn_text,
            ], alignment=ft.MainAxisAlignment.CENTER, spacing=8),
            bgcolor=PRIMARY_TEAL,
            padding=ft.Padding(16, 12, 16, 12),
            border_radius=12,
            alignment=ft.Alignment(0, 0),
            on_click=self._handle_generate_session,
        )

        content = ft.Column([
            ft.Row([engine_badge], alignment=ft.MainAxisAlignment.CENTER),
            ft.Container(height=4),
            title,
            subtitle,
            ft.Container(height=8),
            mode_label,
            modes_row,
            ft.Row([self.mode_subtext], alignment=ft.MainAxisAlignment.CENTER),
            self.quiz_count_section,
            ft.Container(height=6),
            upload_type_row,
            quick_chips_row,
            ft.Container(height=4),
            subject_label,
            self.topic_input,
            self.notes_paste_input,
            self.notes_word_count,
            self.paste_upload_btn,
            self.dropzone_container,
            ft.Container(height=4),
            self.generate_session_btn,
        ], spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)

        return soft_card(content, width=640, padding=24, border_radius=22)


    # ── Center: 2. Summary View Card ─────────────────────────────
    def _build_summary_card(self) -> ft.Control:
        if not self.current_session:
            return self._build_center_workspace_card()

        summary_data = self.current_session.get("summary", {})
        topic_title = summary_data.get("topic") or self.current_session.get("topic", "Lecture Summary")
        overview_text = summary_data.get("overview", "")
        key_concepts = summary_data.get("key_concepts", [])
        formulas_definitions = summary_data.get("formulas_and_definitions", [])
        exam_tips = summary_data.get("high_yield_exam_tips", [])
        has_quiz = bool(self.current_session.get("quiz"))

        # Header with Back & Mode badge
        header_row = ft.Row([
            ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.ARROW_BACK, size=14, color=PRIMARY_TEAL),
                    ft.Text("Back to History" if self.active_nav == "History" else "Back to Upload", size=12, weight=ft.FontWeight.BOLD, color=PRIMARY_TEAL),
                ], spacing=4),
                padding=ft.Padding(10, 5, 10, 5),
                bgcolor=PRIMARY_TEAL_LIGHT,
                border_radius=12,
                border=ft.Border.all(1, PRIMARY_TEAL_BORDER),
                on_click=lambda _: self._show_history_view() if self.active_nav == "History" else self._show_workspace_view(),
            ),
            ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.CHECK_CIRCLE, size=14, color=PRIMARY_TEAL_DARK),
                    ft.Text("30-Minute High-Yield Study Guide", size=11, weight=ft.FontWeight.W_600, color=PRIMARY_TEAL_DARK),
                ], spacing=4),
                padding=ft.Padding(10, 5, 10, 5),
                bgcolor=PRIMARY_TEAL_LIGHT,
                border_radius=12,
            ),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        title = ft.Text(topic_title, size=22, weight=ft.FontWeight.BOLD, color=TEXT_TITLE)

        # Overview Box
        overview_card = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.LIGHTBULB_OUTLINE, size=16, color=PRIMARY_TEAL),
                    ft.Text("Executive Synthesis", size=12, weight=ft.FontWeight.BOLD, color=PRIMARY_TEAL_DARK),
                ], spacing=6),
                ft.Text(overview_text, size=13, color=TEXT_BODY, selectable=True),
            ], spacing=6),
            padding=16,
            bgcolor=INSET_BG,
            border_radius=14,
            border=ft.Border.all(1, BORDER_COLOR),
        )

        # Key Concepts Sections
        concept_widgets = []
        for i, concept in enumerate(key_concepts, 1):
            concept_title = concept.get("title", f"Core Concept {i}")
            bullets = concept.get("bullet_points", [])
            
            bullet_rows = [
                ft.Row([
                    ft.Icon(ft.Icons.FIBER_MANUAL_RECORD, size=8, color=PRIMARY_TEAL),
                    ft.Text(b, size=12, color=TEXT_BODY, expand=True, selectable=True),
                ], vertical_alignment=ft.CrossAxisAlignment.START, spacing=8)
                for b in bullets
            ]

            concept_widgets.append(
                ft.Container(
                    content=ft.Column([
                        ft.Row([
                            ft.Container(
                                content=ft.Text(str(i), size=11, weight=ft.FontWeight.BOLD, color=PRIMARY_TEAL_DARK),
                                width=20,
                                height=20,
                                border_radius=10,
                                bgcolor=PRIMARY_TEAL_LIGHT,
                                alignment=ft.Alignment(0, 0),
                            ),
                            ft.Text(concept_title, size=14, weight=ft.FontWeight.BOLD, color=TEXT_TITLE),
                        ], spacing=8),
                        ft.Column(bullet_rows, spacing=4),
                    ], spacing=8),
                    padding=14,
                    bgcolor=CARD_BG,
                    border_radius=12,
                    border=ft.Border.all(1, BORDER_COLOR),
                )
            )

        # Formulas and Definitions
        formula_widgets = []
        if formulas_definitions:
            formula_items = [
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.CODE_ROUNDED, size=14, color=PRIMARY_TEAL),
                        ft.Text(item, size=12, weight=ft.FontWeight.W_500, color=TEXT_TITLE, expand=True, selectable=True),
                    ], spacing=6),
                    padding=ft.Padding(10, 6, 10, 6),
                    bgcolor=CARD_BG,
                    border_radius=8,
                    border=ft.Border.all(1, BORDER_COLOR),
                )
                for item in formulas_definitions
            ]
            formula_widgets = [
                ft.Text("ESSENTIAL FORMULAS & DEFINITIONS", size=10, weight=ft.FontWeight.BOLD, color=TEXT_MUTED),
                ft.Column(formula_items, spacing=6),
            ]

        # Exam Tips & Common Traps
        tips_widgets = []
        if exam_tips:
            tip_items = [
                ft.Row([
                    ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, size=14, color=ACCENT_ORANGE_DARK),
                    ft.Text(tip, size=12, color=TEXT_BODY, expand=True, selectable=True),
                ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.START)
                for tip in exam_tips
            ]
            tips_card = ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Icon(ft.Icons.STAR, size=16, color=ACCENT_ORANGE_DARK),
                        ft.Text("High-Yield Exam Tips & Traps", size=12, weight=ft.FontWeight.BOLD, color=ACCENT_ORANGE_DARK),
                    ], spacing=6),
                    ft.Column(tip_items, spacing=6),
                ], spacing=8),
                padding=14,
                bgcolor=ACCENT_ORANGE_LIGHT,
                border_radius=12,
                border=ft.Border.all(1, ACCENT_ORANGE_BORDER),
            )
            tips_widgets = [tips_card]

        # Bottom Actions
        bottom_buttons = [
            ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.ARROW_BACK, color=PRIMARY_TEAL, size=16),
                    ft.Text("Upload Another Note", color=PRIMARY_TEAL, size=13, weight=ft.FontWeight.BOLD),
                ], alignment=ft.MainAxisAlignment.CENTER, spacing=6),
                bgcolor=CARD_BG,
                border=ft.Border.all(1.5, PRIMARY_TEAL),
                padding=ft.Padding(16, 12, 16, 12),
                border_radius=12,
                expand=True,
                alignment=ft.Alignment(0, 0),
                on_click=lambda _: self._show_workspace_view(),
            )
        ]

        if has_quiz:
            quiz_count = len(self.current_session.get("quiz", []))
            start_quiz_btn = ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.TIMER_ROUNDED, color=ft.Colors.WHITE, size=18),
                    ft.Text(f"Start 5-Minute Timed Quiz ({quiz_count} Qs) ⚡", color=ft.Colors.WHITE, size=13, weight=ft.FontWeight.BOLD),
                ], alignment=ft.MainAxisAlignment.CENTER, spacing=8),
                bgcolor=PRIMARY_TEAL,
                padding=ft.Padding(16, 12, 16, 12),
                border_radius=12,
                expand=True,
                alignment=ft.Alignment(0, 0),
                on_click=lambda _: asyncio.create_task(self._start_quiz_session()),
            )
            bottom_buttons.append(start_quiz_btn)

        action_row = ft.Row(bottom_buttons, spacing=10)

        summary_content = ft.Column([
            header_row,
            ft.Container(height=4),
            title,
            overview_card,
            ft.Text("KEY CONCEPTS BREAKDOWN", size=10, weight=ft.FontWeight.BOLD, color=TEXT_MUTED),
            ft.Column(concept_widgets, spacing=8),
            *formula_widgets,
            *tips_widgets,
            ft.Container(height=10),
            action_row,
        ], spacing=10, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)

        return soft_card(summary_content, width=640, padding=24, border_radius=22)

    # ── Center: 3. Timed Quiz View Card ──────────────────────────
    def _build_quiz_card(self) -> ft.Control:
        if not self.current_session or not self.current_session.get("quiz"):
            return self._build_center_workspace_card()

        quiz_list = self.current_session.get("quiz", [])
        total_questions = len(quiz_list)
        current_idx = self.quiz_current_index
        q_data = quiz_list[current_idx]
        q_text = q_data.get("question", "")
        options = q_data.get("options", [])

        mins = self.quiz_timer_seconds // 60
        secs = self.quiz_timer_seconds % 60
        time_str = f"{mins:02d}:{secs:02d}"

        self.quiz_timer_text = ft.Text(
            f"⏱ {time_str}",
            size=14,
            weight=ft.FontWeight.BOLD,
            color=ACCENT_ORANGE_DARK if self.quiz_timer_seconds < 60 else PRIMARY_TEAL,
        )

        total_time = float(getattr(self, "quiz_total_timer_seconds", 300) or 300)
        self.quiz_progress_bar = ft.ProgressBar(
            value=max(0.0, min(1.0, self.quiz_timer_seconds / total_time)),
            color=ACCENT_ORANGE_DARK if self.quiz_timer_seconds < 60 else PRIMARY_TEAL,
            bgcolor="#E2E8F0",
            height=6,
            border_radius=3,
        )

        has_summary = bool(self.current_session and self.current_session.get("summary"))
        back_action = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.MENU_BOOK if has_summary else ft.Icons.ARROW_BACK, size=13, color=PRIMARY_TEAL),
                ft.Text("View Summary" if has_summary else "Exit Quiz", size=11, weight=ft.FontWeight.BOLD, color=PRIMARY_TEAL),
            ], spacing=4),
            padding=ft.Padding(8, 4, 8, 4),
            bgcolor=PRIMARY_TEAL_LIGHT,
            border_radius=10,
            on_click=lambda _: self._show_summary_view() if has_summary else self._stop_quiz_and_exit(),
        )

        header_row = ft.Row([
            back_action,
            ft.Text(f"Question {current_idx + 1} of {total_questions}", size=12, weight=ft.FontWeight.BOLD, color=TEXT_TITLE),
            self.quiz_timer_text,
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        # Question Prompt
        question_card = ft.Container(
            content=ft.Column([
                ft.Text(f"Q{current_idx + 1}. {q_text}", size=15, weight=ft.FontWeight.BOLD, color=TEXT_TITLE, selectable=True),
            ]),
            padding=16,
            bgcolor=INSET_BG,
            border_radius=14,
            border=ft.Border.all(1, BORDER_COLOR),
        )

        # 4 Interactive Answer Options
        selected_opt = self.quiz_selected_answers.get(current_idx, -1)
        option_letters = ["A", "B", "C", "D"]
        option_widgets = []

        for opt_idx, opt_text in enumerate(options):
            is_selected = (selected_opt == opt_idx)
            
            def _make_selector(q_i, o_i):
                return lambda _: self._select_quiz_option(q_i, o_i)

            letter_badge = ft.Container(
                content=ft.Text(option_letters[opt_idx], size=11, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE if is_selected else PRIMARY_TEAL),
                width=24,
                height=24,
                border_radius=12,
                bgcolor=PRIMARY_TEAL if is_selected else PRIMARY_TEAL_LIGHT,
                alignment=ft.Alignment(0, 0),
            )

            option_widgets.append(
                ft.Container(
                    content=ft.Row([
                        letter_badge,
                        ft.Text(opt_text, size=13, weight=ft.FontWeight.W_600 if is_selected else ft.FontWeight.NORMAL, color=TEXT_TITLE, expand=True),
                        ft.Icon(ft.Icons.RADIO_BUTTON_CHECKED if is_selected else ft.Icons.RADIO_BUTTON_UNCHECKED, size=18, color=PRIMARY_TEAL if is_selected else TEXT_LIGHT),
                    ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=12,
                    bgcolor=PRIMARY_TEAL_LIGHT if is_selected else CARD_BG,
                    border_radius=12,
                    border=ft.Border.all(1.5 if is_selected else 1, PRIMARY_TEAL if is_selected else BORDER_COLOR),
                    on_click=_make_selector(current_idx, opt_idx),
                )
            )

        # Pager row (Previous, Next, Submit)
        prev_btn = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.ARROW_BACK_IOS, size=12, color=PRIMARY_TEAL if current_idx > 0 else TEXT_LIGHT),
                ft.Text("Previous", size=12, weight=ft.FontWeight.BOLD, color=PRIMARY_TEAL if current_idx > 0 else TEXT_LIGHT),
            ], spacing=4),
            padding=ft.Padding(14, 8, 14, 8),
            bgcolor=PRIMARY_TEAL_LIGHT if current_idx > 0 else CARD_BG_MUTED,
            border_radius=10,
            border=ft.Border.all(1, PRIMARY_TEAL_BORDER if current_idx > 0 else BORDER_COLOR),
            on_click=(lambda _: self._nav_quiz(current_idx - 1)) if current_idx > 0 else None,
        )

        answered_count = len(self.quiz_selected_answers)
        submit_btn = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.CHECK, size=16, color=ft.Colors.WHITE),
                ft.Text(f"Submit Quiz ({answered_count}/{total_questions})", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
            ], spacing=6),
            padding=ft.Padding(16, 8, 16, 8),
            bgcolor=ACCENT_ORANGE if answered_count == total_questions else PRIMARY_TEAL,
            border_radius=10,
            on_click=lambda _: asyncio.create_task(self._submit_quiz()),
        )

        next_btn = ft.Container(
            content=ft.Row([
                ft.Text("Next", size=12, weight=ft.FontWeight.BOLD, color=PRIMARY_TEAL if current_idx < total_questions - 1 else TEXT_LIGHT),
                ft.Icon(ft.Icons.ARROW_FORWARD_IOS, size=12, color=PRIMARY_TEAL if current_idx < total_questions - 1 else TEXT_LIGHT),
            ], spacing=4),
            padding=ft.Padding(14, 8, 14, 8),
            bgcolor=PRIMARY_TEAL_LIGHT if current_idx < total_questions - 1 else CARD_BG_MUTED,
            border_radius=10,
            border=ft.Border.all(1, PRIMARY_TEAL_BORDER if current_idx < total_questions - 1 else BORDER_COLOR),
            on_click=(lambda _: self._nav_quiz(current_idx + 1)) if current_idx < total_questions - 1 else None,
        )

        # Quick question number jumping chips
        quick_jump_chips = []
        for q_i in range(total_questions):
            is_curr = (q_i == current_idx)
            is_done = (q_i in self.quiz_selected_answers)
            
            def _jump(target):
                return lambda _: self._nav_quiz(target)

            quick_jump_chips.append(
                ft.Container(
                    content=ft.Text(str(q_i + 1), size=11, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE if is_curr else (PRIMARY_TEAL if is_done else TEXT_MUTED)),
                    width=28,
                    height=28,
                    border_radius=14,
                    bgcolor=PRIMARY_TEAL if is_curr else (PRIMARY_TEAL_LIGHT if is_done else CARD_BG_MUTED),
                    border=ft.Border.all(1, PRIMARY_TEAL if is_curr or is_done else BORDER_COLOR),
                    alignment=ft.Alignment(0, 0),
                    on_click=_jump(q_i),
                )
            )

        quick_jump_row = ft.Row(quick_jump_chips, spacing=6, alignment=ft.MainAxisAlignment.CENTER)

        quiz_content = ft.Column([
            header_row,
            self.quiz_progress_bar,
            ft.Container(height=6),
            question_card,
            ft.Container(height=4),
            ft.Column(option_widgets, spacing=8),
            ft.Container(height=10),
            ft.Row([prev_btn, submit_btn, next_btn], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Container(height=6),
            quick_jump_row,
        ], spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)

        return soft_card(quiz_content, width=640, padding=24, border_radius=22)

    def _select_quiz_option(self, q_index: int, opt_index: int):
        self.quiz_selected_answers[q_index] = opt_index
        self.center_card_container.content = self._build_quiz_card()
        self.page.update()

    def _nav_quiz(self, target_index: int):
        self.quiz_current_index = target_index
        self.center_card_container.content = self._build_quiz_card()
        self.page.update()

    # ── Center: 4. Quiz Review & Score Card ──────────────────────
    def _build_quiz_review_card(self) -> ft.Control:
        if not self.quiz_results:
            return self._build_center_workspace_card()

        score_pct = self.quiz_results.get("score_percent", 0.0)
        correct_count = self.quiz_results.get("correct_count", 0)
        total_questions = self.quiz_results.get("total_questions", 0)
        xp_earned = self.quiz_results.get("xp_earned", 0)
        details = self.quiz_results.get("details", [])

        # Score Banner
        is_high_pass = (score_pct >= 80)
        score_banner = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.EMOJI_EVENTS if is_high_pass else ft.Icons.CHECK_CIRCLE, size=32, color=PRIMARY_TEAL),
                    ft.Column([
                        ft.Text(f"{score_pct}% Score", size=24, weight=ft.FontWeight.BOLD, color=TEXT_TITLE),
                        ft.Text(f"{correct_count} of {total_questions} Questions Correct", size=13, color=TEXT_MUTED),
                    ], spacing=2),
                    ft.Container(
                        content=ft.Row([
                            ft.Icon(ft.Icons.BOLT, color=ft.Colors.WHITE, size=16),
                            ft.Text(f"+{xp_earned} XP", color=ft.Colors.WHITE, size=13, weight=ft.FontWeight.BOLD),
                        ], spacing=4),
                        padding=ft.Padding(12, 6, 12, 6),
                        bgcolor=PRIMARY_TEAL,
                        border_radius=16,
                    ),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ]),
            padding=20,
            bgcolor=PRIMARY_TEAL_LIGHT if is_high_pass else INSET_BG,
            border_radius=16,
            border=ft.Border.all(1.5, PRIMARY_TEAL_BORDER if is_high_pass else BORDER_COLOR),
        )

        # Question-by-question review items
        review_widgets = []
        for d in details:
            q_i = d.get("question_index", 0)
            q_text = d.get("question", "")
            options = d.get("options", [])
            sel_idx = d.get("selected_option_index", -1)
            corr_idx = d.get("correct_answer_index", 0)
            is_corr = d.get("is_correct", False)
            expl = d.get("explanation", "")

            user_ans_text = options[sel_idx] if (0 <= sel_idx < len(options)) else "Not Answered"
            corr_ans_text = options[corr_idx] if (0 <= corr_idx < len(options)) else ""

            status_icon = ft.Icon(ft.Icons.CHECK_CIRCLE if is_corr else ft.Icons.CANCEL, size=18, color=PRIMARY_TEAL if is_corr else ft.Colors.RED_500)
            status_text = ft.Text("Correct (+10 XP)" if is_corr else "Incorrect", size=12, weight=ft.FontWeight.BOLD, color=PRIMARY_TEAL if is_corr else ft.Colors.RED_500)

            explanation_box = ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.INFO_OUTLINE, size=14, color=PRIMARY_TEAL),
                    ft.Text(f"Explanation: {expl}", size=11, color=TEXT_BODY, expand=True, selectable=True),
                ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.START),
                padding=10,
                bgcolor=CARD_BG,
                border_radius=8,
                border=ft.Border.all(1, BORDER_COLOR),
            )

            review_widgets.append(
                ft.Container(
                    content=ft.Column([
                        ft.Row([
                            ft.Row([status_icon, status_text], spacing=6),
                            ft.Text(f"Q{q_i + 1}", size=12, weight=ft.FontWeight.BOLD, color=TEXT_MUTED),
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        ft.Text(q_text, size=13, weight=ft.FontWeight.BOLD, color=TEXT_TITLE, selectable=True),
                        ft.Row([
                            ft.Text("Your Answer:", size=11, color=TEXT_MUTED),
                            ft.Text(user_ans_text, size=11, weight=ft.FontWeight.BOLD, color=PRIMARY_TEAL if is_corr else ft.Colors.RED_500),
                        ], spacing=6),
                        ft.Row([
                            ft.Text("Correct Answer:", size=11, color=TEXT_MUTED),
                            ft.Text(corr_ans_text, size=11, weight=ft.FontWeight.BOLD, color=PRIMARY_TEAL),
                        ], spacing=6) if not is_corr else ft.Container(),
                        explanation_box,
                    ], spacing=6),
                    padding=14,
                    bgcolor=CARD_BG_MUTED,
                    border_radius=12,
                    border=ft.Border.all(1, BORDER_COLOR),
                )
            )

        # Action Buttons
        has_summary = bool(self.current_session and self.current_session.get("summary"))
        action_row = ft.Row([
            ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.MENU_BOOK if has_summary else ft.Icons.HISTORY_ROUNDED, color=PRIMARY_TEAL, size=16),
                    ft.Text("Review Summary" if has_summary else "Study History", color=PRIMARY_TEAL, size=12, weight=ft.FontWeight.BOLD),
                ], spacing=6, alignment=ft.MainAxisAlignment.CENTER),
                bgcolor=CARD_BG,
                border=ft.Border.all(1.5, PRIMARY_TEAL),
                padding=ft.Padding(14, 10, 14, 10),
                border_radius=12,
                expand=True,
                alignment=ft.Alignment(0, 0),
                on_click=lambda _: self._show_summary_view() if has_summary else self._show_history_view(),
            ),
            ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.REPLAY, color=PRIMARY_TEAL, size=16),
                    ft.Text("Retake Quiz", color=PRIMARY_TEAL, size=12, weight=ft.FontWeight.BOLD),
                ], spacing=6, alignment=ft.MainAxisAlignment.CENTER),
                bgcolor=PRIMARY_TEAL_LIGHT,
                border=ft.Border.all(1.5, PRIMARY_TEAL),
                padding=ft.Padding(14, 10, 14, 10),
                border_radius=12,
                expand=True,
                alignment=ft.Alignment(0, 0),
                on_click=lambda _: asyncio.create_task(self._start_quiz_session()),
            ),
            ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.ADD, color=ft.Colors.WHITE, size=16),
                    ft.Text("New Session", color=ft.Colors.WHITE, size=12, weight=ft.FontWeight.BOLD),
                ], spacing=6, alignment=ft.MainAxisAlignment.CENTER),
                bgcolor=PRIMARY_TEAL,
                padding=ft.Padding(14, 10, 14, 10),
                border_radius=12,
                expand=True,
                alignment=ft.Alignment(0, 0),
                on_click=lambda _: self._show_workspace_view(),
            ),
        ], spacing=10)

        content = ft.Column([
            ft.Text("QUIZ RESULTS & REVIEW", size=10, weight=ft.FontWeight.BOLD, color=TEXT_MUTED),
            score_banner,
            ft.Container(height=4),
            ft.Text("QUESTION-BY-QUESTION BREAKDOWN", size=10, weight=ft.FontWeight.BOLD, color=TEXT_MUTED),
            ft.Column(review_widgets, spacing=8),
            ft.Container(height=10),
            action_row,
        ], spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)

        return soft_card(content, width=640, padding=24, border_radius=22)


    # ── Center: 5. Study History Section Card ────────────────────
    def _build_history_card(self) -> ft.Control:
        """Renders the comprehensive Study History section in the center card."""
        mega_button_text = "Exit Mega Quiz" if self.mega_quiz_mode else "⚡ Mega Quiz Builder"
        mega_button_bgcolor = INSET_BG if self.mega_quiz_mode else ACCENT_ORANGE_LIGHT
        mega_button_color = TEXT_TITLE if self.mega_quiz_mode else ACCENT_ORANGE_DARK
        mega_button_border = ft.Border.all(1, BORDER_COLOR if self.mega_quiz_mode else ACCENT_ORANGE)

        header_row = ft.Row([
            ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.ARROW_BACK, size=14, color=PRIMARY_TEAL),
                    ft.Text("Back to Workspace", size=12, weight=ft.FontWeight.W_600, color=PRIMARY_TEAL),
                ], spacing=4),
                padding=ft.Padding(10, 6, 10, 6),
                bgcolor=PRIMARY_TEAL_LIGHT,
                border_radius=8,
                border=ft.Border.all(1, PRIMARY_TEAL_BORDER),
                on_click=lambda _: self._show_workspace_view(),
            ),
            ft.Row([
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.CLOSE if self.mega_quiz_mode else ft.Icons.ELECTRIC_BOLT_ROUNDED, size=14, color=mega_button_color),
                        ft.Text(mega_button_text, size=12, weight=ft.FontWeight.BOLD, color=mega_button_color),
                    ], spacing=4),
                    padding=ft.Padding(10, 6, 10, 6),
                    bgcolor=mega_button_bgcolor,
                    border_radius=8,
                    border=mega_button_border,
                    on_click=lambda _: self._toggle_mega_quiz_mode(),
                ),
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.REFRESH_ROUNDED, size=14, color=PRIMARY_TEAL),
                        ft.Text("Refresh", size=12, weight=ft.FontWeight.W_600, color=PRIMARY_TEAL),
                    ], spacing=4),
                    padding=ft.Padding(10, 6, 10, 6),
                    bgcolor=CARD_BG,
                    border_radius=8,
                    border=ft.Border.all(1, BORDER_COLOR),
                    on_click=lambda _: asyncio.create_task(self._fetch_history_from_backend(notify_user=True)),
                ),
            ], spacing=8),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        engine_badge = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.HISTORY_ROUNDED, color=PRIMARY_TEAL, size=14),
                ft.Text("STUDY HISTORY • PERSISTENT", size=10, weight=ft.FontWeight.BOLD, color=PRIMARY_TEAL),
            ], spacing=5, tight=True),
            padding=ft.Padding(10, 4, 10, 4),
            bgcolor=PRIMARY_TEAL_LIGHT,
            border_radius=20,
            border=ft.Border.all(1, PRIMARY_TEAL_BORDER),
        )

        title = ft.Text("Your Generated Study Materials", size=20, weight=ft.FontWeight.BOLD, color=TEXT_TITLE)
        subtitle = ft.Text(
            "Access, review, or delete your previously generated AI study notes and practice quizzes.",
            size=12,
            color=TEXT_MUTED,
        )

        total_count = len(self.history_items)
        meta_chips = ft.Row([
            ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.AUTO_STORIES_OUTLINED, size=13, color=PRIMARY_TEAL),
                    ft.Text(f"{total_count} Study Session{'s' if total_count != 1 else ''}", size=11, weight=ft.FontWeight.W_600, color=PRIMARY_TEAL),
                ], spacing=4),
                padding=ft.Padding(8, 4, 8, 4),
                bgcolor=PRIMARY_TEAL_LIGHT,
                border_radius=12,
            ),
            ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.SWAP_VERT_ROUNDED, size=13, color=TEXT_MUTED),
                    ft.Text("Newest First", size=11, color=TEXT_MUTED),
                ], spacing=4),
                padding=ft.Padding(8, 4, 8, 4),
                bgcolor=INSET_BG,
                border_radius=12,
                border=ft.Border.all(1, BORDER_COLOR),
            ),
        ], spacing=8)

        # Mega Quiz Interactive Banner
        mega_banner = None
        if self.mega_quiz_mode:
            selected_count = len(self.mega_quiz_selected_ids)
            total_mega_questions = 0
            for it in self.history_items:
                sid = it.get("session_id") or it.get("history_id")
                if sid in self.mega_quiz_selected_ids:
                    q_list = it.get("quiz", [])
                    if isinstance(q_list, list):
                        total_mega_questions += len(q_list)

            can_launch = (selected_count >= 1 and total_mega_questions > 0)
            mega_banner = ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Row([
                            ft.Icon(ft.Icons.ELECTRIC_BOLT_ROUNDED, size=16, color=ACCENT_ORANGE_DARK),
                            ft.Text("Mega Quiz Builder Active", size=13, weight=ft.FontWeight.BOLD, color=TEXT_TITLE),
                        ], spacing=6),
                        ft.Row([
                            ft.TextButton("Select All (Quizzes)", on_click=lambda _: self._mega_quiz_select_all(True)),
                            ft.TextButton("Clear", on_click=lambda _: self._mega_quiz_select_all(False)),
                        ], spacing=2),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ft.Text(
                        "Check the boxes on multiple past study sessions below to pool and deduplicate all practice questions into one unified master exam.",
                        size=11,
                        color=TEXT_BODY,
                    ),
                    ft.Row([
                        ft.Text(
                            f"{selected_count} session(s) selected • {total_mega_questions} questions pooled",
                            size=12,
                            weight=ft.FontWeight.W_600,
                            color=PRIMARY_TEAL_DARK,
                        ),
                        ft.Container(
                            content=ft.Row([
                                ft.Icon(ft.Icons.PLAY_ARROW_ROUNDED, size=15, color=ft.Colors.WHITE if can_launch else TEXT_LIGHT),
                                ft.Text(
                                    f"Start Mega Quiz ({total_mega_questions} Qs) ⚡" if can_launch else "Select sessions to start",
                                    size=12,
                                    weight=ft.FontWeight.BOLD,
                                    color=ft.Colors.WHITE if can_launch else TEXT_LIGHT,
                                ),
                            ], spacing=6, tight=True),
                            padding=ft.Padding(14, 8, 14, 8),
                            bgcolor=PRIMARY_TEAL if can_launch else INSET_BG,
                            border_radius=10,
                            disabled=not can_launch,
                            on_click=lambda _: asyncio.create_task(self._start_mega_quiz()),
                        ),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ], spacing=8),
                padding=14,
                bgcolor=ACCENT_ORANGE_LIGHT,
                border_radius=14,
                border=ft.Border.all(1.5, ACCENT_ORANGE),
            )

        if not self.history_items:
            content_area = ft.Container(
                content=ft.Column([
                    ft.Container(height=16),
                    ft.Container(
                        content=ft.Icon(ft.Icons.HISTORY_EDU_ROUNDED, size=36, color=PRIMARY_TEAL),
                        width=64,
                        height=64,
                        border_radius=32,
                        bgcolor=PRIMARY_TEAL_LIGHT,
                        border=ft.Border.all(1.5, PRIMARY_TEAL_BORDER),
                        alignment=ft.Alignment(0, 0),
                    ),
                    ft.Text("No Study History Yet", size=16, weight=ft.FontWeight.BOLD, color=TEXT_TITLE),
                    ft.Text(
                        "You haven't generated any study sessions yet.\nUpload lecture slides or paste notes in the workspace to get started!",
                        size=12,
                        color=TEXT_MUTED,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Container(height=8),
                    ft.Container(
                        content=ft.Row([
                            ft.Icon(ft.Icons.ADD, size=16, color=ft.Colors.WHITE),
                            ft.Text("Create First Study Guide", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                        ], spacing=6, tight=True),
                        padding=ft.Padding(16, 10, 16, 10),
                        bgcolor=PRIMARY_TEAL,
                        border_radius=12,
                        on_click=lambda _: self._show_workspace_view(),
                    ),
                    ft.Container(height=16),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
                alignment=ft.Alignment(0, 0),
            )
        else:
            cards = [self._build_history_record_tile(item) for item in self.history_items]
            content_area = ft.Column(cards, spacing=12)

        content_items = [
            header_row,
            ft.Container(height=4),
            ft.Row([engine_badge], alignment=ft.MainAxisAlignment.START),
            title,
            subtitle,
            meta_chips,
        ]
        if mega_banner:
            content_items.append(mega_banner)
        content_items.extend([
            ft.Container(height=6),
            content_area,
        ])
        content = ft.Column(content_items, spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)

        return soft_card(content, width=640, padding=24, border_radius=22)


    def _build_history_record_tile(self, item: dict) -> ft.Control:
        """Renders an individual study session card for the History list view."""
        topic_title = item.get("topic") or "Study Session"
        orig_file = item.get("original_filename") or f"{topic_title}.txt"
        mode_val = item.get("mode", "both").lower()
        created_at_raw = item.get("created_at", "")
        h_id = item.get("session_id") or item.get("history_id", "")
        is_mega = item.get("is_mega_quiz", False)
        is_selected = (h_id in self.mega_quiz_selected_ids)

        # Format ISO timestamp
        formatted_date = created_at_raw
        if created_at_raw:
            try:
                clean_iso = created_at_raw.replace("Z", "+00:00")
                dt = datetime.fromisoformat(clean_iso)
                formatted_date = dt.strftime("%b %d, %Y • %I:%M %p")
            except Exception:
                formatted_date = created_at_raw[:19].replace("T", " ")

        summary_data = item.get("summary", {})
        if not isinstance(summary_data, dict):
            summary_data = {}
        overview_text = summary_data.get("overview", "")
        if len(overview_text) > 130:
            overview_snippet = overview_text[:127] + "..."
        else:
            overview_snippet = overview_text

        concepts_count = len(summary_data.get("key_concepts", []))
        formulas_count = len(summary_data.get("formulas_and_definitions", []))
        quiz_list = item.get("quiz", [])
        quiz_count = len(quiz_list) if isinstance(quiz_list, list) else 0

        if is_mega:
            mode_badge_text = "MEGA QUIZ ⚡"
        else:
            mode_badge_text = "SUMMARY + QUIZ" if mode_val == "both" else ("QUIZ ONLY" if mode_val == "quiz" else "SUMMARY ONLY")

        stat_chips = []
        if is_mega:
            stat_chips.append(
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.ELECTRIC_BOLT_ROUNDED, size=11, color=ACCENT_ORANGE_DARK),
                        ft.Text("Mega Exam", size=10, weight=ft.FontWeight.BOLD, color=ACCENT_ORANGE_DARK),
                    ], spacing=3, tight=True),
                    padding=ft.Padding(6, 2, 6, 2),
                    bgcolor=ACCENT_ORANGE_LIGHT,
                    border_radius=8,
                )
            )
        elif concepts_count > 0:
            stat_chips.append(
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.LIGHTBULB_OUTLINE, size=11, color=PRIMARY_TEAL),
                        ft.Text(f"{concepts_count} Concepts", size=10, weight=ft.FontWeight.W_600, color=PRIMARY_TEAL),
                    ], spacing=3, tight=True),
                    padding=ft.Padding(6, 2, 6, 2),
                    bgcolor=PRIMARY_TEAL_LIGHT,
                    border_radius=8,
                )
            )
        if formulas_count > 0:
            stat_chips.append(
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.FUNCTIONS, size=11, color=TEXT_MUTED),
                        ft.Text(f"{formulas_count} Formulas", size=10, color=TEXT_MUTED),
                    ], spacing=3, tight=True),
                    padding=ft.Padding(6, 2, 6, 2),
                    bgcolor=CARD_BG_MUTED,
                    border_radius=8,
                )
            )
        if quiz_count > 0:
            stat_chips.append(
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.TIMER_OUTLINED, size=11, color=ACCENT_ORANGE_DARK),
                        ft.Text(f"{quiz_count} Questions", size=10, weight=ft.FontWeight.W_600, color=ACCENT_ORANGE_DARK),
                    ], spacing=3, tight=True),
                    padding=ft.Padding(6, 2, 6, 2),
                    bgcolor=ACCENT_ORANGE_LIGHT,
                    border_radius=8,
                )
            )

        mega_select_row = None
        if self.mega_quiz_mode:
            if quiz_count > 0:
                mega_select_row = ft.Container(
                    content=ft.Row([
                        ft.Checkbox(
                            value=is_selected,
                            label=f"Include in Mega Quiz ({quiz_count} Qs available)",
                            label_style=ft.TextStyle(size=12, weight=ft.FontWeight.BOLD, color=PRIMARY_TEAL_DARK if is_selected else TEXT_TITLE),
                            on_change=lambda e, sid=h_id: self._on_mega_session_toggled(sid, e.control.value),
                        ),
                    ], alignment=ft.MainAxisAlignment.START),
                    padding=ft.Padding(8, 2, 8, 2),
                    bgcolor=PRIMARY_TEAL_LIGHT if is_selected else INSET_BG,
                    border_radius=8,
                    border=ft.Border.all(1.5 if is_selected else 1, PRIMARY_TEAL if is_selected else BORDER_COLOR),
                )
            else:
                mega_select_row = ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.INFO_OUTLINE, size=13, color=TEXT_MUTED),
                        ft.Text("Summary only (0 quiz questions to pool)", size=11, color=TEXT_MUTED, italic=True),
                    ], spacing=4),
                    padding=ft.Padding(8, 4, 8, 4),
                    bgcolor=INSET_BG,
                    border_radius=8,
                )

        action_buttons = []
        if is_mega:
            action_buttons.append(
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.BOLT, size=14, color=ft.Colors.WHITE),
                        ft.Text(f"Take Mega Quiz ({quiz_count} Qs)", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                    ], spacing=6, tight=True),
                    padding=ft.Padding(14, 8, 14, 8),
                    bgcolor=ACCENT_ORANGE,
                    border_radius=8,
                    on_click=lambda _, it=item: self._load_and_start_quiz(it),
                )
            )
        else:
            action_buttons.append(
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.MENU_BOOK_ROUNDED, size=14, color=ft.Colors.WHITE),
                        ft.Text("Open Study Guide", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                    ], spacing=6, tight=True),
                    padding=ft.Padding(14, 8, 14, 8),
                    bgcolor=PRIMARY_TEAL,
                    border_radius=8,
                    on_click=lambda _, it=item: self._load_history_item(it),
                )
            )
            if quiz_count > 0:
                action_buttons.append(
                    ft.Container(
                        content=ft.Row([
                            ft.Icon(ft.Icons.PLAY_ARROW_ROUNDED, size=14, color=PRIMARY_TEAL),
                            ft.Text("Take Quiz", size=12, weight=ft.FontWeight.BOLD, color=PRIMARY_TEAL),
                        ], spacing=4, tight=True),
                        padding=ft.Padding(12, 8, 12, 8),
                        bgcolor=PRIMARY_TEAL_LIGHT,
                        border_radius=8,
                        border=ft.Border.all(1, PRIMARY_TEAL_BORDER),
                        on_click=lambda _, it=item: self._load_and_start_quiz(it),
                    )
                )

        card_content_items = []
        if mega_select_row:
            card_content_items.append(mega_select_row)

        card_content_items.extend([
            # Top row: mode badge, date, and delete icon
            ft.Row([
                ft.Row([
                    ft.Container(
                        content=ft.Text(mode_badge_text, size=9, weight=ft.FontWeight.BOLD, color=ACCENT_ORANGE_DARK if is_mega else PRIMARY_TEAL),
                        padding=ft.Padding(6, 2, 6, 2),
                        bgcolor=ACCENT_ORANGE_LIGHT if is_mega else PRIMARY_TEAL_LIGHT,
                        border_radius=6,
                        border=ft.Border.all(1, ACCENT_ORANGE if is_mega else PRIMARY_TEAL_BORDER),
                    ),
                    ft.Row([
                        ft.Icon(ft.Icons.CALENDAR_TODAY_OUTLINED, size=11, color=TEXT_LIGHT),
                        ft.Text(formatted_date, size=10, color=TEXT_LIGHT),
                    ], spacing=4),
                ], spacing=8),
                ft.IconButton(
                    icon=ft.Icons.DELETE_OUTLINE_ROUNDED,
                    icon_color=TEXT_LIGHT,
                    icon_size=16,
                    tooltip="Delete from history",
                    on_click=lambda _, it=item: self._confirm_delete_history(it),
                ),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),

            # Topic title
            ft.Text(topic_title, size=15, weight=ft.FontWeight.BOLD, color=TEXT_TITLE),

            # File name
            ft.Row([
                ft.Icon(ft.Icons.DESCRIPTION_OUTLINED, size=13, color=PRIMARY_TEAL),
                ft.Text(f"Source: {orig_file}", size=11, weight=ft.FontWeight.W_500, color=TEXT_MUTED),
            ], spacing=4),

            # Overview preview
            ft.Text(overview_snippet or ("Pooled mega practice quiz questions." if is_mega else "Generated study notes and practice questions."), size=11, color=TEXT_BODY, italic=True),

            # Stat pills
            ft.Row(stat_chips, spacing=6),

            ft.Container(height=4),

            # Action buttons
            ft.Row(action_buttons, spacing=8),
        ])

        card_content = ft.Column(card_content_items, spacing=6)

        return ft.Container(
            content=card_content,
            padding=ft.Padding(16, 14, 16, 14),
            bgcolor=PRIMARY_TEAL_LIGHT if (self.mega_quiz_mode and is_selected) else CARD_BG,
            border_radius=14,
            border=ft.Border.all(
                2 if (self.mega_quiz_mode and is_selected) else 1,
                PRIMARY_TEAL if (self.mega_quiz_mode and is_selected) else BORDER_COLOR
            ),
            shadow=SOFT_SHADOW,
        )

    # ── Center: 6. Achievements & Gamification Section Card ─────
    def _build_achievements_card(self) -> ft.Control:
        """Renders the comprehensive Achievements, Badges, and Scholar Progression view."""
        streak_val = self.user.get("streak", 0)
        xp_val = self.user.get("xp", 0)
        level_val = 1 + (xp_val // 200)
        uploads_count = self.user.get("total_uploads", 0)
        best_score = float(self.user.get("best_quiz_score", 0.0))
        best_score_str = f"{int(best_score)}%" if best_score > 0 else "--"

        level_titles = {
            1: "Newcomer",
            2: "Student",
            3: "Learner",
            4: "Scholar",
            5: "Expert",
            6: "Academic Legend"
        }
        level_title = level_titles.get(min(6, level_val), "Academic Legend" if level_val >= 6 else "Scholar")
        xp_in_level = xp_val % 200
        xp_to_next = 200 - xp_in_level
        progress_val = min(1.0, xp_in_level / 200.0)

        # Header Row: Back to workspace + Sync stats
        header_row = ft.Row([
            ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.ARROW_BACK, size=14, color=PRIMARY_TEAL),
                    ft.Text("Back to Workspace", size=12, weight=ft.FontWeight.W_600, color=PRIMARY_TEAL),
                ], spacing=4),
                padding=ft.Padding(10, 6, 10, 6),
                bgcolor=PRIMARY_TEAL_LIGHT,
                border_radius=8,
                border=ft.Border.all(1, PRIMARY_TEAL_BORDER),
                on_click=lambda _: self._show_workspace_view(),
            ),
            ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.SYNC_ROUNDED, size=14, color=PRIMARY_TEAL),
                    ft.Text("Sync Stats", size=12, weight=ft.FontWeight.W_600, color=PRIMARY_TEAL),
                ], spacing=4),
                padding=ft.Padding(10, 6, 10, 6),
                bgcolor=CARD_BG,
                border_radius=8,
                border=ft.Border.all(1, BORDER_COLOR),
                on_click=lambda _: asyncio.create_task(self._refresh_user_profile(notify_user=True)),
            ),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        engine_badge = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.MILITARY_TECH_ROUNDED, color=ACCENT_ORANGE, size=14),
                ft.Text("SCHOLAR PROGRESSION & ACHIEVEMENTS", size=10, weight=ft.FontWeight.BOLD, color=ACCENT_ORANGE_DARK),
            ], spacing=5, tight=True),
            padding=ft.Padding(10, 4, 10, 4),
            bgcolor=ACCENT_ORANGE_LIGHT,
            border_radius=20,
            border=ft.Border.all(1, ACCENT_ORANGE_BORDER),
        )

        title = ft.Text("Achievements & Academic Milestones", size=20, weight=ft.FontWeight.BOLD, color=TEXT_TITLE)
        subtitle = ft.Text(
            "Track your study experience, unlock badges, and advance your scholar rank by learning daily.",
            size=12,
            color=TEXT_MUTED,
        )

        # Hero Level & Stats Card
        avatar_box = ft.Container(
            content=ft.Icon(ft.Icons.SCHOOL_ROUNDED, size=28, color=ft.Colors.WHITE),
            width=54,
            height=54,
            border_radius=27,
            bgcolor=PRIMARY_TEAL,
            alignment=ft.Alignment(0, 0),
        )

        level_info = ft.Column([
            ft.Row([
                ft.Text(f"Level {level_val} • {level_title}", size=17, weight=ft.FontWeight.BOLD, color=TEXT_TITLE),
                ft.Container(
                    content=ft.Text(f"RANK TIER {min(6, level_val)}/6", size=10, weight=ft.FontWeight.BOLD, color=PRIMARY_TEAL),
                    padding=ft.Padding(6, 2, 6, 2),
                    bgcolor=PRIMARY_TEAL_LIGHT,
                    border_radius=10,
                    border=ft.Border.all(1, PRIMARY_TEAL_BORDER),
                ),
            ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Text(f"{xp_val} Total XP Earned • Dedicated StudyBuddy Scholar", size=11, color=TEXT_MUTED),
        ], spacing=2)

        streak_hero_badge = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.LOCAL_FIRE_DEPARTMENT, size=14, color=ACCENT_ORANGE_DARK),
                ft.Text(f"{streak_val} Day Streak", size=11, weight=ft.FontWeight.BOLD, color=ACCENT_ORANGE_DARK),
            ], spacing=4),
            padding=ft.Padding(10, 5, 10, 5),
            bgcolor=ACCENT_ORANGE_LIGHT,
            border_radius=14,
            border=ft.Border.all(1, ACCENT_ORANGE_BORDER),
        )

        hero_top_row = ft.Row([
            ft.Row([avatar_box, level_info], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            streak_hero_badge,
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.CENTER)

        xp_bar = ft.ProgressBar(
            value=progress_val,
            color=PRIMARY_TEAL,
            bgcolor="#E2E8F0",
            height=8,
            border_radius=4,
        )

        xp_subtext_row = ft.Row([
            ft.Text(f"Lv.{level_val} ({xp_in_level}/200 XP)", size=11, color=TEXT_MUTED),
            ft.Text(f"{xp_to_next} XP needed for Lv.{level_val + 1} ({int(progress_val * 100)}%)", size=11, weight=ft.FontWeight.W_600, color=PRIMARY_TEAL),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        def make_stat_tile(icon, label, value, val_color=TEXT_TITLE):
            return ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Icon(icon, size=13, color=PRIMARY_TEAL),
                        ft.Text(label, size=10, color=TEXT_MUTED),
                    ], spacing=4),
                    ft.Text(value, size=15, weight=ft.FontWeight.BOLD, color=val_color),
                ], spacing=2),
                padding=ft.Padding(12, 8, 12, 8),
                bgcolor=CARD_BG,
                border_radius=10,
                border=ft.Border.all(1, BORDER_COLOR),
                expand=True,
            )

        quick_stats_row = ft.Row([
            make_stat_tile(ft.Icons.BOLT, "Total XP", f"{xp_val} XP"),
            make_stat_tile(ft.Icons.LOCAL_FIRE_DEPARTMENT, "Streak", f"{streak_val}d", ACCENT_ORANGE_DARK),
            make_stat_tile(ft.Icons.FACT_CHECK_ROUNDED, "Best Quiz", best_score_str, PRIMARY_TEAL),
            make_stat_tile(ft.Icons.AUTO_STORIES_ROUNDED, "Uploads", f"{uploads_count} Docs"),
        ], spacing=8)

        hero_card = ft.Container(
            content=ft.Column([
                hero_top_row,
                ft.Container(height=4),
                xp_bar,
                xp_subtext_row,
                ft.Container(height=4),
                quick_stats_row,
            ], spacing=6),
            padding=ft.Padding(16, 14, 16, 14),
            bgcolor=INSET_BG,
            border_radius=14,
            border=ft.Border.all(1, PRIMARY_TEAL_BORDER),
        )

        # 8 Badges Definitions & Live State Evaluation
        badges_set = set(self.user.get("badges", []))
        if xp_val >= 50:
            badges_set.add("first")
        if best_score >= 80:
            badges_set.add("quiz")
        if best_score >= 100:
            badges_set.add("legend")
        if uploads_count >= 3:
            badges_set.add("scholar")
        if streak_val >= 3:
            badges_set.add("week")
        if xp_val >= 400:
            badges_set.add("master")
        if xp_val >= 800:
            badges_set.add("prodigy")

        badges_definitions = [
            {
                "id": "first",
                "name": "First Step",
                "reward": "+50 XP",
                "icon": ft.Icons.ROCKET_LAUNCH_ROUNDED,
                "desc": "Generate your first AI study guide & summary notes.",
                "req": "Earn 50+ XP from your first study session",
                "unlocked": "first" in badges_set or xp_val >= 50,
            },
            {
                "id": "quiz",
                "name": "Quiz Ace",
                "reward": "+75 XP",
                "icon": ft.Icons.FACT_CHECK_ROUNDED,
                "desc": "Demonstrate exam readiness with a score of 80% or higher.",
                "req": "Score ≥ 80% on any practice quiz",
                "unlocked": "quiz" in badges_set or best_score >= 80,
            },
            {
                "id": "speed",
                "name": "Speed Learner",
                "reward": "+50 XP",
                "icon": ft.Icons.BOLT_ROUNDED,
                "desc": "Complete a timed practice quiz in under 2 minutes with ≥ 60%.",
                "req": "Finish timed quiz in ≤ 120s with passing score",
                "unlocked": "speed" in badges_set,
            },
            {
                "id": "scholar",
                "name": "Resourceful Scholar",
                "reward": "+100 XP",
                "icon": ft.Icons.AUTO_STORIES_ROUNDED,
                "desc": "Upload 3 or more lecture documents to your study workspace.",
                "req": f"Upload 3 lecture files (Current: {uploads_count}/3)",
                "unlocked": "scholar" in badges_set or uploads_count >= 3,
            },
            {
                "id": "week",
                "name": "Consistent Scholar",
                "reward": "+100 XP",
                "icon": ft.Icons.LOCAL_FIRE_DEPARTMENT_ROUNDED,
                "desc": "Maintain an active study habit across 3 consecutive days.",
                "req": f"Reach 3-day study streak (Current: {streak_val}/3)",
                "unlocked": "week" in badges_set or streak_val >= 3,
            },
            {
                "id": "legend",
                "name": "Century Club",
                "reward": "+150 XP",
                "icon": ft.Icons.WORKSPACE_PREMIUM_ROUNDED,
                "desc": "Attain absolute academic perfection with a 100% quiz score.",
                "req": "Score a perfect 100% on any practice quiz",
                "unlocked": "legend" in badges_set or best_score >= 100,
            },
            {
                "id": "master",
                "name": "Honor Roll",
                "reward": "+200 XP",
                "icon": ft.Icons.SCHOOL_ROUNDED,
                "desc": "Advance to Scholar Level 3 through persistent study preparation.",
                "req": "Advance to Level 3 (400+ total XP)",
                "unlocked": "master" in badges_set or xp_val >= 400,
            },
            {
                "id": "prodigy",
                "name": "Academic Titan",
                "reward": "+300 XP",
                "icon": ft.Icons.DIAMOND_ROUNDED,
                "desc": "Advance to Scholar Level 5 and solidify academic mastery.",
                "req": "Advance to Level 5 (800+ total XP)",
                "unlocked": "prodigy" in badges_set or xp_val >= 800,
            },
        ]

        unlocked_count = sum(1 for b in badges_definitions if b["unlocked"])
        badge_pct = int((unlocked_count / len(badges_definitions)) * 100)

        badge_section_header = ft.Row([
            ft.Row([
                ft.Icon(ft.Icons.MILITARY_TECH_ROUNDED, size=16, color=PRIMARY_TEAL),
                ft.Text("SCHOLAR BADGES", size=12, weight=ft.FontWeight.BOLD, color=TEXT_TITLE),
            ], spacing=6),
            ft.Container(
                content=ft.Row([
                    ft.Text(f"{unlocked_count}/8 Unlocked", size=11, weight=ft.FontWeight.BOLD, color=PRIMARY_TEAL),
                    ft.Text(f"• {badge_pct}%", size=11, color=TEXT_MUTED),
                ], spacing=3),
                padding=ft.Padding(8, 3, 8, 3),
                bgcolor=PRIMARY_TEAL_LIGHT,
                border_radius=10,
                border=ft.Border.all(1, PRIMARY_TEAL_BORDER),
            ),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        def make_badge_card(b: dict) -> ft.Container:
            is_unlocked = b["unlocked"]
            icon_color = PRIMARY_TEAL if is_unlocked else TEXT_LIGHT
            icon_bg = PRIMARY_TEAL_LIGHT if is_unlocked else INSET_BG
            card_border = PRIMARY_TEAL_BORDER if is_unlocked else BORDER_COLOR
            card_bg = CARD_BG if is_unlocked else CARD_BG_MUTED

            status_pill = ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.CHECK_CIRCLE_ROUNDED, size=11, color=PRIMARY_TEAL),
                    ft.Text("UNLOCKED", size=9, weight=ft.FontWeight.BOLD, color=PRIMARY_TEAL),
                ], spacing=3, tight=True) if is_unlocked else ft.Row([
                    ft.Icon(ft.Icons.LOCK_OUTLINE_ROUNDED, size=11, color=TEXT_LIGHT),
                    ft.Text(b["req"], size=9, color=TEXT_MUTED, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                ], spacing=3, tight=True),
                padding=ft.Padding(6, 2, 6, 2),
                bgcolor=PRIMARY_TEAL_LIGHT if is_unlocked else INSET_BG,
                border_radius=8,
            )

            reward_chip = ft.Container(
                content=ft.Text(b["reward"], size=9, weight=ft.FontWeight.BOLD, color=PRIMARY_TEAL if is_unlocked else TEXT_MUTED),
                padding=ft.Padding(5, 2, 5, 2),
                bgcolor=PRIMARY_TEAL_LIGHT if is_unlocked else INSET_BG,
                border_radius=6,
            )

            badge_content = ft.Row([
                ft.Container(
                    content=ft.Icon(b["icon"], size=22, color=icon_color),
                    width=40,
                    height=40,
                    border_radius=10,
                    bgcolor=icon_bg,
                    alignment=ft.Alignment(0, 0),
                ),
                ft.Column([
                    ft.Row([
                        ft.Text(b["name"], size=12, weight=ft.FontWeight.BOLD, color=TEXT_TITLE if is_unlocked else TEXT_MUTED),
                        reward_chip,
                    ], spacing=6, alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ft.Text(b["desc"], size=10, color=TEXT_MUTED, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                    status_pill,
                ], spacing=3, expand=True),
            ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER)

            return ft.Container(
                content=badge_content,
                padding=ft.Padding(10, 8, 10, 8),
                bgcolor=card_bg,
                border_radius=12,
                border=ft.Border.all(1, card_border),
                expand=True,
            )

        badge_rows = []
        for i in range(0, len(badges_definitions), 2):
            b1 = badges_definitions[i]
            b2 = badges_definitions[i+1] if i+1 < len(badges_definitions) else None
            row_items = [make_badge_card(b1)]
            if b2:
                row_items.append(make_badge_card(b2))
            badge_rows.append(ft.Row(row_items, spacing=8))

        # Scholar Progression Roadmap
        roadmap_header = ft.Row([
            ft.Row([
                ft.Icon(ft.Icons.TRENDING_UP_ROUNDED, size=16, color=PRIMARY_TEAL),
                ft.Text("SCHOLAR PROGRESSION ROADMAP", size=12, weight=ft.FontWeight.BOLD, color=TEXT_TITLE),
            ], spacing=6),
            ft.Text("200 XP Per Rank Tier", size=11, color=TEXT_MUTED),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        roadmap_tiers = [
            (1, "Newcomer", "0–199 XP", "Foundation study generator and 30-min summaries"),
            (2, "Student", "200–399 XP", "Timed 5-minute practice quizzes unlocked"),
            (3, "Learner", "400–599 XP", "Honor Roll badge unlocked & advanced exam tips"),
            (4, "Scholar", "600–799 XP", "Detailed performance analytics & accuracy metrics"),
            (5, "Expert", "800–999 XP", "Academic Titan badge unlocked & deep reasoning"),
            (6, "Academic Legend", "1000+ XP", "Prestige title and supreme mastery across all subjects"),
        ]

        roadmap_items = []
        for tier_lvl, tier_name, tier_xp, tier_perk in roadmap_tiers:
            is_current = (level_val == tier_lvl) or (tier_lvl == 6 and level_val >= 6)
            is_past = level_val > tier_lvl

            if is_current:
                tag = ft.Container(
                    content=ft.Text("CURRENT RANK", size=9, weight=ft.FontWeight.BOLD, color=PRIMARY_TEAL),
                    padding=ft.Padding(6, 2, 6, 2),
                    bgcolor=PRIMARY_TEAL_LIGHT,
                    border_radius=6,
                    border=ft.Border.all(1, PRIMARY_TEAL_BORDER),
                )
                status_icon = ft.Icon(ft.Icons.STAR_ROUNDED, size=15, color=PRIMARY_TEAL)
                row_bg = PRIMARY_TEAL_LIGHT
                row_border = PRIMARY_TEAL_BORDER
            elif is_past:
                tag = ft.Text("Completed", size=10, weight=ft.FontWeight.W_600, color=PRIMARY_TEAL)
                status_icon = ft.Icon(ft.Icons.CHECK_CIRCLE, size=14, color=PRIMARY_TEAL)
                row_bg = CARD_BG
                row_border = BORDER_COLOR
            else:
                tag = ft.Text("Locked", size=10, color=TEXT_LIGHT)
                status_icon = ft.Icon(ft.Icons.LOCK_OUTLINE, size=14, color=TEXT_LIGHT)
                row_bg = CARD_BG_MUTED
                row_border = BORDER_COLOR

            roadmap_items.append(
                ft.Container(
                    content=ft.Row([
                        status_icon,
                        ft.Text(f"Tier {tier_lvl}: {tier_name}", size=11, weight=ft.FontWeight.BOLD if is_current else ft.FontWeight.W_600, color=TEXT_TITLE if (is_current or is_past) else TEXT_MUTED),
                        ft.Text(tier_xp, size=10, weight=ft.FontWeight.W_600, color=PRIMARY_TEAL if is_current else TEXT_MUTED),
                        ft.Text(tier_perk, size=10, color=TEXT_MUTED, expand=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                        tag,
                    ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=ft.Padding(10, 6, 10, 6),
                    bgcolor=row_bg,
                    border_radius=8,
                    border=ft.Border.all(1, row_border),
                )
            )

        # XP Earning Guide Card
        def make_xp_guide_tile(icon, title_txt, xp_txt, subtitle_txt):
            return ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Icon(icon, size=14, color=PRIMARY_TEAL),
                        ft.Text(title_txt, size=11, weight=ft.FontWeight.BOLD, color=TEXT_TITLE),
                    ], spacing=4),
                    ft.Text(xp_txt, size=14, weight=ft.FontWeight.BOLD, color=PRIMARY_TEAL),
                    ft.Text(subtitle_txt, size=10, color=TEXT_MUTED),
                ], spacing=2),
                padding=ft.Padding(12, 8, 12, 8),
                bgcolor=CARD_BG,
                border_radius=10,
                border=ft.Border.all(1, BORDER_COLOR),
                expand=True,
            )

        xp_guide_row = ft.Row([
            make_xp_guide_tile(ft.Icons.AUTO_STORIES_ROUNDED, "AI Study Session", "+50 XP", "Generate study notes"),
            make_xp_guide_tile(ft.Icons.FACT_CHECK_ROUNDED, "Practice Quiz", "+10 to +30 XP", "+25 XP for 80%+, +50 for 100%"),
            make_xp_guide_tile(ft.Icons.LOCAL_FIRE_DEPARTMENT_ROUNDED, "Daily Streak", "+20 XP/day", "Login & study daily"),
        ], spacing=8)

        # Bottom Actions
        action_row = ft.Row([
            ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.DASHBOARD_ROUNDED, size=14, color=ft.Colors.WHITE),
                    ft.Text("Start New Study Prep", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                ], spacing=6, tight=True),
                padding=ft.Padding(16, 10, 16, 10),
                bgcolor=PRIMARY_TEAL,
                border_radius=10,
                on_click=lambda _: self._show_workspace_view(),
            ),
            ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.PLAY_ARROW_ROUNDED, size=14, color=PRIMARY_TEAL),
                    ft.Text("Practice Quiz", size=12, weight=ft.FontWeight.BOLD, color=PRIMARY_TEAL),
                ], spacing=4, tight=True),
                padding=ft.Padding(14, 10, 14, 10),
                bgcolor=PRIMARY_TEAL_LIGHT,
                border_radius=10,
                border=ft.Border.all(1, PRIMARY_TEAL_BORDER),
                on_click=lambda _: asyncio.create_task(self._start_quiz_session()) if (self.current_session and self.current_session.get("quiz")) else self._notify("Generate or select a study pack first to take a quiz.", is_info=False),
            ),
        ], spacing=8)

        content = ft.Column([
            header_row,
            ft.Container(height=2),
            engine_badge,
            title,
            subtitle,
            ft.Divider(height=1, color=BORDER_COLOR),
            hero_card,
            ft.Container(height=4),
            badge_section_header,
            *badge_rows,
            ft.Container(height=4),
            roadmap_header,
            *roadmap_items,
            ft.Container(height=4),
            xp_guide_row,
            ft.Divider(height=1, color=BORDER_COLOR),
            action_row,
        ], spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)

        return soft_card(content, width=640, padding=24, border_radius=22)

    # ── Center: 7. Student Profile & Subject Skill Radar Card ────
    def _build_spider_chart(self, skills: dict) -> ft.Control:
        """
        Renders a dynamic N-axis Radar / Spider Chart using flet.canvas.Canvas.
        Visualizes student mastery strictly across the academic disciplines they have actual study history for.
        """
        import math
        import flet.canvas as cv

        if not skills:
            return ft.Container(
                content=ft.Column([
                    ft.Container(
                        content=ft.Icon(ft.Icons.RADAR_ROUNDED, size=28, color=TEXT_LIGHT),
                        width=56, height=56, border_radius=28,
                        bgcolor=CARD_BG_MUTED,
                        border=ft.Border.all(1, BORDER_COLOR),
                        alignment=ft.Alignment(0, 0),
                    ),
                    ft.Text("No Study History Yet", size=13, weight=ft.FontWeight.BOLD, color=TEXT_BODY, text_align=ft.TextAlign.CENTER),
                    ft.Text(
                        "Upload study notes or take practice quizzes to calibrate your personal Subject Mastery Radar!",
                        size=11, color=TEXT_MUTED, text_align=ft.TextAlign.CENTER
                    ),
                ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=6),
                width=300,
                height=280,
                alignment=ft.Alignment(0, 0),
                padding=16,
                bgcolor=INSET_BG,
                border_radius=16,
                border=ft.Border.all(1, BORDER_COLOR),
            )

        num_subjects = len(skills)
        if num_subjects < 3:
            # 1 or 2 subjects: cannot form a 2D closed polygon geometrically
            return ft.Container(
                content=ft.Column([
                    ft.Container(
                        content=ft.Icon(ft.Icons.AUTO_GRAPH_ROUNDED, size=28, color=PRIMARY_TEAL),
                        width=56, height=56, border_radius=28,
                        bgcolor=PRIMARY_TEAL_LIGHT,
                        border=ft.Border.all(1, PRIMARY_TEAL_BORDER),
                        alignment=ft.Alignment(0, 0),
                    ),
                    ft.Text("Radar Unlocks at 3 Subjects", size=13, weight=ft.FontWeight.BOLD, color=TEXT_TITLE, text_align=ft.TextAlign.CENTER),
                    ft.Text(
                        f"You've calibrated {num_subjects} subject area{'s' if num_subjects != 1 else ''} so far. Study {3 - num_subjects} more distinct subject to generate your 360° competency spider polygon!",
                        size=11, color=TEXT_MUTED, text_align=ft.TextAlign.CENTER
                    ),
                    ft.Container(
                        content=ft.Text(f"{num_subjects}/3 Active Subjects", size=10, weight=ft.FontWeight.BOLD, color=PRIMARY_TEAL_DARK),
                        padding=ft.Padding(10, 4, 10, 4),
                        bgcolor=PRIMARY_TEAL_LIGHT,
                        border_radius=12,
                    ),
                ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=6),
                width=300,
                height=280,
                alignment=ft.Alignment(0, 0),
                padding=16,
                bgcolor=INSET_BG,
                border_radius=16,
                border=ft.Border.all(1, BORDER_COLOR),
            )

        # 3 or more subjects: render dynamic polygon radar chart
        cx, cy, R = 150.0, 140.0, 85.0
        abbrevs = {
            "Computer Architecture & Hardware": "Arch",
            "Algorithms & Data Structures": "Algo",
            "Digital Logic & Circuits": "Logic",
            "Software Engineering & Web": "Dev",
            "Biology & Life Sciences": "Bio",
            "Social Sciences & Humanities": "Social",
            "Mathematics & Statistics": "Math",
            "Physics & Physical Sciences": "Phys",
            "Chemistry & Molecular Sciences": "Chem",
            "Business & Economics": "Econ",
            "Language & Literature": "Lang",
        }

        axes = []
        for name, val in skills.items():
            short = abbrevs.get(name)
            if not short:
                words = name.split()
                short = words[0][:4] if words else name[:4]
            axes.append((name, short, float(val)))

        num_axes = len(axes)
        shapes = []

        # 1. Concentric background polygon grid rings (25%, 50%, 75%, 100%)
        grid_color = "#E2E8F0"
        for step in [0.25, 0.50, 0.75, 1.0]:
            ring_r = R * step
            pts = []
            for i in range(num_axes):
                angle = -math.pi / 2 + i * (2 * math.pi / num_axes)
                x = cx + ring_r * math.cos(angle)
                y = cy + ring_r * math.sin(angle)
                pts.append((x, y))

            ring_path = cv.Path(
                [cv.Path.MoveTo(pts[0][0], pts[0][1])] +
                [cv.Path.LineTo(px, py) for px, py in pts[1:]] +
                [cv.Path.Close()],
                paint=ft.Paint(color=grid_color, stroke_width=1.0, style=ft.PaintingStyle.STROKE)
            )
            shapes.append(ring_path)

            # Ring percentage indicator
            shapes.append(
                cv.Text(
                    cx + 3,
                    cy - ring_r - 6,
                    f"{int(step * 100)}%",
                    ft.TextStyle(size=8, color="#94A3B8", weight=ft.FontWeight.W_500)
                )
            )

        # 2. Radial Spoke Lines from center to outer ring
        for i in range(num_axes):
            angle = -math.pi / 2 + i * (2 * math.pi / num_axes)
            outer_x = cx + R * math.cos(angle)
            outer_y = cy + R * math.sin(angle)
            shapes.append(
                cv.Line(
                    cx, cy, outer_x, outer_y,
                    paint=ft.Paint(color="#E2E8F0", stroke_width=1.0)
                )
            )

        # 3. User Skill Data Polygon
        data_pts = []
        for i, (subject_name, short_code, val) in enumerate(axes):
            pct = max(15.0, min(100.0, val)) / 100.0
            angle = -math.pi / 2 + i * (2 * math.pi / num_axes)
            data_r = R * pct
            x = cx + data_r * math.cos(angle)
            y = cy + data_r * math.sin(angle)
            data_pts.append((x, y))

        # Filled translucent polygon
        fill_path = cv.Path(
            [cv.Path.MoveTo(data_pts[0][0], data_pts[0][1])] +
            [cv.Path.LineTo(px, py) for px, py in data_pts[1:]] +
            [cv.Path.Close()],
            paint=ft.Paint(color="#330D9488", style=ft.PaintingStyle.FILL)
        )
        shapes.append(fill_path)

        # Solid outline stroke
        stroke_path = cv.Path(
            [cv.Path.MoveTo(data_pts[0][0], data_pts[0][1])] +
            [cv.Path.LineTo(px, py) for px, py in data_pts[1:]] +
            [cv.Path.Close()],
            paint=ft.Paint(color=PRIMARY_TEAL, stroke_width=2.5, style=ft.PaintingStyle.STROKE)
        )
        shapes.append(stroke_path)

        # 4. Data Vertex Dots
        for px, py in data_pts:
            shapes.append(
                cv.Circle(px, py, 4.0, paint=ft.Paint(color=PRIMARY_TEAL, style=ft.PaintingStyle.FILL))
            )
            shapes.append(
                cv.Circle(px, py, 1.8, paint=ft.Paint(color=ft.Colors.WHITE, style=ft.PaintingStyle.FILL))
            )

        # 5. Outer Subject Axis Labels
        for i, (subject_name, short_code, val) in enumerate(axes):
            angle = -math.pi / 2 + i * (2 * math.pi / num_axes)
            label_dist = R + 22
            lx = cx + label_dist * math.cos(angle)
            ly = cy + label_dist * math.sin(angle)

            cos_val = math.cos(angle)
            sin_val = math.sin(angle)
            if abs(cos_val) < 0.2:
                offset_x = 22.0
                offset_y = 12.0 if sin_val < 0 else -2.0
            elif cos_val > 0:
                offset_x = 4.0
                offset_y = 6.0
            else:
                offset_x = 48.0
                offset_y = 6.0

            shapes.append(
                cv.Text(
                    lx - offset_x,
                    ly - offset_y,
                    f"{short_code} ({int(val)}%)",
                    ft.TextStyle(size=10, weight=ft.FontWeight.BOLD, color=PRIMARY_TEAL_DARK)
                )
            )

        # Center pulse circle
        shapes.append(
            cv.Circle(cx, cy, 3.0, paint=ft.Paint(color=PRIMARY_TEAL_DARK, style=ft.PaintingStyle.FILL))
        )

        return cv.Canvas(shapes, width=300, height=280)

    def _build_profile_card(self) -> ft.Control:
        """Renders the comprehensive Student Profile, Identity, Stats, and Subject Skill Radar."""
        name = self.user.get("name", "Student")
        email = self.user.get("email", "")
        plan = self.user.get("plan", "free")
        is_pro = (plan == "pro")
        streak_val = self.user.get("streak", 0)
        xp_val = self.user.get("xp", 0)
        level_val = 1 + (xp_val // 200)
        uploads_count = self.user.get("total_uploads", 0)
        best_score = float(self.user.get("best_quiz_score", 0.0))
        requests_today = self.user.get("requests_today", 0)
        created_at_raw = self.user.get("created_at", "")
        total_sessions = len(self.history_items)

        # Format Member Since date
        member_since = "Active Student"
        if created_at_raw:
            try:
                clean_iso = created_at_raw.replace("Z", "+00:00")
                dt = datetime.fromisoformat(clean_iso)
                member_since = f"Member since {dt.strftime('%b %d, %Y')}"
            except Exception:
                member_since = f"Member since {created_at_raw[:10]}"

        level_titles = {
            1: "Newcomer Scholar",
            2: "Dedicated Student",
            3: "Active Learner",
            4: "Master Scholar",
            5: "Academic Expert",
            6: "Academic Legend"
        }
        level_title = level_titles.get(min(6, level_val), "Scholar")

        # Top Header Navigation Row
        header_row = ft.Row([
            ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.ARROW_BACK, size=14, color=PRIMARY_TEAL),
                    ft.Text("Back to Workspace", size=12, weight=ft.FontWeight.W_600, color=PRIMARY_TEAL),
                ], spacing=4),
                padding=ft.Padding(10, 6, 10, 6),
                bgcolor=PRIMARY_TEAL_LIGHT,
                border_radius=8,
                border=ft.Border.all(1, PRIMARY_TEAL_BORDER),
                on_click=lambda _: self._show_workspace_view(),
            ),
            ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.REFRESH_ROUNDED, size=14, color=PRIMARY_TEAL),
                    ft.Text("Sync Profile", size=12, weight=ft.FontWeight.W_600, color=PRIMARY_TEAL),
                ], spacing=4),
                padding=ft.Padding(10, 6, 10, 6),
                bgcolor=CARD_BG,
                border_radius=8,
                border=ft.Border.all(1, BORDER_COLOR),
                on_click=lambda _: asyncio.create_task(self._refresh_user_profile(notify_user=True)),
            ),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        engine_badge = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.PERSON_PIN_ROUNDED, color=PRIMARY_TEAL, size=14),
                ft.Text("STUDENT PROFILE • ACADEMIC RECORD", size=10, weight=ft.FontWeight.BOLD, color=PRIMARY_TEAL),
            ], spacing=5, tight=True),
            padding=ft.Padding(10, 4, 10, 4),
            bgcolor=PRIMARY_TEAL_LIGHT,
            border_radius=20,
            border=ft.Border.all(1, PRIMARY_TEAL_BORDER),
        )

        # 1. User Identity Hero Card
        avatar_circle = ft.CircleAvatar(
            content=ft.Text(name[0].upper() if name else "S", size=24, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
            radius=30,
            bgcolor=PRIMARY_TEAL,
        )

        plan_badge = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.CHECK_CIRCLE if is_pro else ft.Icons.LOCK_OUTLINE, size=13, color=ft.Colors.WHITE if is_pro else ACCENT_ORANGE_DARK),
                ft.Text("StudyBuddy Pro Active" if is_pro else "Free Plan (3/day)", size=11, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE if is_pro else ACCENT_ORANGE_DARK),
            ], spacing=4, tight=True),
            padding=ft.Padding(10, 4, 10, 4),
            bgcolor=PRIMARY_TEAL if is_pro else ACCENT_ORANGE_LIGHT,
            border_radius=12,
            border=ft.Border.all(1, PRIMARY_TEAL_BORDER if is_pro else ACCENT_ORANGE),
        )

        user_info_col = ft.Column([
            ft.Row([
                ft.Text(name, size=20, weight=ft.FontWeight.BOLD, color=TEXT_TITLE),
                plan_badge,
            ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Text(email, size=12, color=TEXT_MUTED),
            ft.Row([
                ft.Container(
                    content=ft.Text(f"Lv.{level_val} {level_title}", size=10, weight=ft.FontWeight.BOLD, color=PRIMARY_TEAL_DARK),
                    padding=ft.Padding(8, 2, 8, 2),
                    bgcolor=PRIMARY_TEAL_LIGHT,
                    border_radius=8,
                ),
                ft.Text(f"•  {member_since}", size=11, color=TEXT_MUTED),
            ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ], spacing=3, expand=True)

        profile_logout_btn = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.LOGOUT_ROUNDED, size=14, color=ft.Colors.RED_500),
                ft.Text("Log Out", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.RED_600),
            ], spacing=5, tight=True),
            padding=ft.Padding(12, 8, 14, 8),
            bgcolor="#FEF2F2",
            border_radius=10,
            border=ft.Border.all(1, "#FECACA"),
            tooltip="Sign out of StudyBuddy",
            on_click=lambda _: self._show_user_menu(),
        )

        hero_identity_card = ft.Container(
            content=ft.Row([
                avatar_circle,
                user_info_col,
                profile_logout_btn,
            ], spacing=16, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding(18, 14, 18, 14),
            bgcolor=CARD_BG,
            border_radius=16,
            border=ft.Border.all(1, BORDER_COLOR),
            shadow=SOFT_SHADOW,
        )

        # 2. Key Academic Stats Grid (4 Cards)
        xp_in_level = xp_val % 200
        xp_pct = max(0.0, min(1.0, xp_in_level / 200.0))

        def make_stat_tile(icon, label, value_str, sub_text, icon_color, bg_color):
            return ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Icon(icon, size=16, color=icon_color),
                        ft.Text(label, size=10, weight=ft.FontWeight.BOLD, color=TEXT_MUTED),
                    ], spacing=6),
                    ft.Text(value_str, size=16, weight=ft.FontWeight.BOLD, color=TEXT_TITLE),
                    ft.Text(sub_text, size=10, color=TEXT_MUTED),
                ], spacing=2),
                padding=ft.Padding(12, 10, 12, 10),
                bgcolor=bg_color,
                border_radius=12,
                border=ft.Border.all(1, BORDER_COLOR),
                expand=True,
            )

        stat_tile_1 = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.TRENDING_UP_ROUNDED, size=16, color=PRIMARY_TEAL),
                    ft.Text("SCHOLAR LEVEL", size=10, weight=ft.FontWeight.BOLD, color=TEXT_MUTED),
                ], spacing=6),
                ft.Text(f"Lv. {level_val} ({xp_val} XP)", size=16, weight=ft.FontWeight.BOLD, color=TEXT_TITLE),
                ft.ProgressBar(value=xp_pct, color=PRIMARY_TEAL, bgcolor="#E2E8F0", height=5, border_radius=3),
                ft.Text(f"{xp_in_level}/200 XP to Lv.{level_val + 1}", size=9, color=TEXT_MUTED),
            ], spacing=3),
            padding=ft.Padding(12, 10, 12, 10),
            bgcolor=CARD_BG,
            border_radius=12,
            border=ft.Border.all(1, BORDER_COLOR),
            expand=True,
        )

        stat_tile_2 = make_stat_tile(
            ft.Icons.EMOJI_EVENTS_ROUNDED, "BEST QUIZ SCORE",
            f"{int(best_score)}%" if best_score > 0 else "--",
            "Highest exam accuracy",
            "#B45309", CARD_BG
        )
        stat_tile_3 = make_stat_tile(
            ft.Icons.LOCAL_FIRE_DEPARTMENT_ROUNDED, "STUDY STREAK",
            f"{streak_val} Days",
            "Consecutive study days",
            ACCENT_ORANGE_DARK, CARD_BG
        )
        stat_tile_4 = make_stat_tile(
            ft.Icons.AUTO_STORIES_ROUNDED, "STUDY SESSIONS",
            f"{total_sessions}",
            f"{uploads_count} uploaded docs",
            PRIMARY_TEAL, CARD_BG
        )

        stats_row = ft.Row([stat_tile_1, stat_tile_2, stat_tile_3, stat_tile_4], spacing=8)

        # 3. Subject Skills Radar Chart & Mastery Breakdown (strictly from user history)
        skills_map = self.user.get("subject_skills") or {}
        spider_chart_widget = self._build_spider_chart(skills_map)

        icon_mapping = {
            "Computer Architecture & Hardware": ft.Icons.MEMORY_ROUNDED,
            "Algorithms & Data Structures": ft.Icons.ACCOUNT_TREE_ROUNDED,
            "Digital Logic & Circuits": ft.Icons.DEVELOPER_BOARD_ROUNDED,
            "Software Engineering & Web": ft.Icons.TERMINAL_ROUNDED,
            "Biology & Life Sciences": ft.Icons.BIOTECH_ROUNDED,
            "Social Sciences & Humanities": ft.Icons.PUBLIC_ROUNDED,
            "Mathematics & Statistics": ft.Icons.FUNCTIONS_ROUNDED,
            "Physics & Physical Sciences": ft.Icons.SPEED_ROUNDED,
            "Chemistry & Molecular Sciences": ft.Icons.SCIENCE_ROUNDED,
            "Business & Economics": ft.Icons.SAVINGS_ROUNDED,
            "General Academic Studies": ft.Icons.AUTO_STORIES_ROUNDED,
        }

        breakdown_rows = []
        if not skills_map:
            breakdown_rows.append(
                ft.Container(
                    content=ft.Column([
                        ft.Icon(ft.Icons.AUTO_STORIES_OUTLINED, size=24, color=TEXT_LIGHT),
                        ft.Text("No subjects calibrated yet", size=12, weight=ft.FontWeight.BOLD, color=TEXT_MUTED),
                        ft.Text("Upload lecture materials or complete practice quizzes to track your subject skills.", size=10, color=TEXT_LIGHT, text_align=ft.TextAlign.CENTER),
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=4),
                    padding=16,
                    alignment=ft.Alignment(0, 0),
                )
            )
        else:
            for s_name, s_val in skills_map.items():
                s_icon = icon_mapping.get(s_name, ft.Icons.SCHOOL_ROUNDED)
                val_float = float(s_val)
                if val_float >= 80:
                    tier_label = "Mastery"
                    tier_color = PRIMARY_TEAL
                    tier_bg = PRIMARY_TEAL_LIGHT
                elif val_float >= 65:
                    tier_label = "Proficient"
                    tier_color = "#2563EB"
                    tier_bg = "#EFF6FF"
                elif val_float >= 50:
                    tier_label = "Intermediate"
                    tier_color = ACCENT_ORANGE_DARK
                    tier_bg = ACCENT_ORANGE_LIGHT
                else:
                    tier_label = "Developing"
                    tier_color = "#64748B"
                    tier_bg = "#F1F5F9"

                breakdown_rows.append(
                    ft.Container(
                        content=ft.Column([
                            ft.Row([
                                ft.Row([
                                    ft.Icon(s_icon, size=13, color=tier_color),
                                    ft.Text(s_name, size=11, weight=ft.FontWeight.W_600, color=TEXT_TITLE),
                                ], spacing=5),
                                ft.Row([
                                    ft.Container(
                                        content=ft.Text(tier_label, size=9, weight=ft.FontWeight.BOLD, color=tier_color),
                                        padding=ft.Padding(5, 1, 5, 1),
                                        bgcolor=tier_bg,
                                        border_radius=6,
                                    ),
                                    ft.Text(f"{int(val_float)}%", size=11, weight=ft.FontWeight.BOLD, color=TEXT_TITLE),
                                ], spacing=6),
                            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                            ft.ProgressBar(value=val_float / 100.0, color=tier_color, bgcolor="#E2E8F0", height=4, border_radius=2),
                        ], spacing=3),
                        padding=ft.Padding(6, 4, 6, 4),
                    )
                )

        radar_card_content = ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.AUTO_GRAPH_ROUNDED, size=16, color=PRIMARY_TEAL),
                ft.Text("SUBJECT MASTERY RADAR", size=12, weight=ft.FontWeight.BOLD, color=TEXT_TITLE),
            ], spacing=6),
            ft.Text(
                "Real-time visual map of your academic competencies across core subjects, continuously calibrated from your generated study materials and practice exam scores.",
                size=11,
                color=TEXT_MUTED,
            ),
            ft.Container(height=4),
            ft.Row([
                # Left Column: Spider Chart
                ft.Container(
                    content=spider_chart_widget,
                    width=300,
                    alignment=ft.Alignment(0, 0),
                ),
                # Right Column: Breakdown List
                ft.Container(
                    content=ft.Column(breakdown_rows, spacing=4),
                    expand=True,
                    padding=ft.Padding(0, 8, 0, 8),
                ),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
        ], spacing=6)

        radar_section_card = ft.Container(
            content=radar_card_content,
            padding=16,
            bgcolor=CARD_BG,
            border_radius=16,
            border=ft.Border.all(1, BORDER_COLOR),
            shadow=SOFT_SHADOW,
        )

        # 4. Premium Subscription & Perks Card
        requests_left = max(0, 3 - requests_today)
        has_discount = (xp_val > 250)

        if is_pro:
            plan_perks_content = ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.WORKSPACE_PREMIUM_ROUNDED, size=18, color=PRIMARY_TEAL),
                    ft.Text("StudyBuddy Pro • Unlimited Plan", size=14, weight=ft.FontWeight.BOLD, color=TEXT_TITLE),
                ], spacing=6),
                ft.Text(
                    "You have active Pro access with unlimited daily generations, Mega Quiz multi-session pooling, and 20-question deep practice quizzes.",
                    size=11, color=TEXT_MUTED
                ),
                ft.Row([
                    ft.Container(
                        content=ft.Row([ft.Icon(ft.Icons.CHECK, size=12, color=PRIMARY_TEAL), ft.Text("Unlimited Generations", size=10, weight=ft.FontWeight.W_600, color=PRIMARY_TEAL)], spacing=3),
                        padding=ft.Padding(8, 3, 8, 3), bgcolor=PRIMARY_TEAL_LIGHT, border_radius=8,
                    ),
                    ft.Container(
                        content=ft.Row([ft.Icon(ft.Icons.CHECK, size=12, color=PRIMARY_TEAL), ft.Text("Mega Exam Builder", size=10, weight=ft.FontWeight.W_600, color=PRIMARY_TEAL)], spacing=3),
                        padding=ft.Padding(8, 3, 8, 3), bgcolor=PRIMARY_TEAL_LIGHT, border_radius=8,
                    ),
                    ft.Container(
                        content=ft.Row([ft.Icon(ft.Icons.CHECK, size=12, color=PRIMARY_TEAL), ft.Text("Fast Flash AI", size=10, weight=ft.FontWeight.W_600, color=PRIMARY_TEAL)], spacing=3),
                        padding=ft.Padding(8, 3, 8, 3), bgcolor=PRIMARY_TEAL_LIGHT, border_radius=8,
                    ),
                ], spacing=6),
            ], spacing=6)
        else:
            plan_perks_content = ft.Column([
                ft.Row([
                    ft.Row([
                        ft.Icon(ft.Icons.AUTO_AWESOME, size=18, color=ACCENT_ORANGE),
                        ft.Text("Free Tier • 3 Daily AI Preps", size=13, weight=ft.FontWeight.BOLD, color=TEXT_TITLE),
                    ], spacing=6),
                    ft.Text(f"{requests_today}/3 Used ({requests_left} left today)", size=11, weight=ft.FontWeight.W_600, color=TEXT_MUTED),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                *(
                    [
                        ft.Container(
                            content=ft.Row([
                                ft.Icon(ft.Icons.DISCOUNT_ROUNDED, size=14, color=PRIMARY_TEAL),
                                ft.Text(
                                    "🎓 Scholar Discount Active: You have over 250 XP, giving you 5% OFF StudyBuddy Pro (৳474.05)!",
                                    size=11, weight=ft.FontWeight.BOLD, color=PRIMARY_TEAL_DARK
                                ),
                            ], spacing=6),
                            padding=ft.Padding(10, 6, 10, 6),
                            bgcolor=PRIMARY_TEAL_LIGHT,
                            border_radius=8,
                        )
                    ] if has_discount else [
                        ft.Text("Earn 250+ XP from practice quizzes to unlock a 5% Scholar Discount on Pro Upgrade!", size=11, color=TEXT_MUTED)
                    ]
                ),
                ft.Row([
                    ft.Container(
                        content=ft.Row([
                            ft.Icon(ft.Icons.BOLT, color=ft.Colors.WHITE, size=15),
                            ft.Text("Upgrade to StudyBuddy Pro ⚡", color=ft.Colors.WHITE, size=12, weight=ft.FontWeight.BOLD),
                        ], spacing=6, tight=True),
                        padding=ft.Padding(16, 8, 16, 8),
                        bgcolor=ACCENT_ORANGE,
                        border_radius=10,
                        on_click=lambda _: self._show_pro_modal(),
                    ),
                ], alignment=ft.MainAxisAlignment.START),
            ], spacing=8)

        plan_card = ft.Container(
            content=plan_perks_content,
            padding=16,
            bgcolor=CARD_BG,
            border_radius=16,
            border=ft.Border.all(1, BORDER_COLOR),
            shadow=SOFT_SHADOW,
        )

        # Bottom Actions
        action_row = ft.Row([
            ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.DASHBOARD_ROUNDED, size=14, color=ft.Colors.WHITE),
                    ft.Text("Back to Workspace", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                ], spacing=6, tight=True),
                padding=ft.Padding(16, 10, 16, 10),
                bgcolor=PRIMARY_TEAL,
                border_radius=10,
                on_click=lambda _: self._show_workspace_view(),
            ),
            ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.HISTORY_ROUNDED, size=14, color=PRIMARY_TEAL),
                    ft.Text("Study History", size=12, weight=ft.FontWeight.BOLD, color=PRIMARY_TEAL),
                ], spacing=4, tight=True),
                padding=ft.Padding(14, 10, 14, 10),
                bgcolor=PRIMARY_TEAL_LIGHT,
                border_radius=10,
                border=ft.Border.all(1, PRIMARY_TEAL_BORDER),
                on_click=lambda _: self._show_history_view(),
            ),
            ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.EMOJI_EVENTS_OUTLINED, size=14, color=TEXT_TITLE),
                    ft.Text("Achievements", size=12, weight=ft.FontWeight.BOLD, color=TEXT_TITLE),
                ], spacing=4, tight=True),
                padding=ft.Padding(14, 10, 14, 10),
                bgcolor=INSET_BG,
                border_radius=10,
                border=ft.Border.all(1, BORDER_COLOR),
                on_click=lambda _: self._show_achievements_view(),
            ),
            ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.LOGOUT_ROUNDED, size=14, color=ft.Colors.RED_600),
                    ft.Text("Log Out", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.RED_600),
                ], spacing=4, tight=True),
                padding=ft.Padding(14, 10, 14, 10),
                bgcolor="#FEF2F2",
                border_radius=10,
                border=ft.Border.all(1, "#FECACA"),
                on_click=lambda _: self._show_user_menu(),
            ),
        ], spacing=8)

        content = ft.Column([
            header_row,
            ft.Container(height=2),
            ft.Row([engine_badge], alignment=ft.MainAxisAlignment.START),
            ft.Text("Scholar Profile & Academic Intelligence", size=20, weight=ft.FontWeight.BOLD, color=TEXT_TITLE),
            ft.Text("Review your academic achievements, multi-disciplinary subject skills, and subscription tier.", size=12, color=TEXT_MUTED),
            ft.Divider(height=1, color=BORDER_COLOR),
            hero_identity_card,
            ft.Container(height=2),
            stats_row,
            ft.Container(height=4),
            radar_section_card,
            ft.Container(height=4),
            plan_card,
            ft.Divider(height=1, color=BORDER_COLOR),
            action_row,
        ], spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)

        return soft_card(content, width=640, padding=24, border_radius=22)

    # ── Main Render ──────────────────────────────────────────────
    def render(self) -> ft.Control:
        navbar = self._build_navbar()

        # Initialize sidebar and center containers
        self.left_history_container.content = self._build_left_history_card_content()
        self.right_achievements_container.content = self._build_right_achievements_card_content()
        self.center_card_container.content = self._build_center_workspace_card()

        # Schedule initial background load of persistent history & profile achievements
        try:
            asyncio.create_task(self._fetch_history_from_backend())
            asyncio.create_task(self._refresh_user_profile())
        except RuntimeError:
            pass

        main_content_row = ft.Row([
            self.left_history_container,
            self.center_card_container,
            self.right_achievements_container,
        ], alignment=ft.MainAxisAlignment.CENTER, vertical_alignment=ft.CrossAxisAlignment.START, spacing=16)

        return ft.Container(
            content=ft.Column([
                navbar,
                ft.Container(
                    content=main_content_row,
                    padding=ft.Padding(20, 0, 20, 20),
                    alignment=ft.Alignment(0, -1),
                ),
            ], spacing=0, scroll=ft.ScrollMode.ADAPTIVE),
            bgcolor=BG_COLOR,
            expand=True,
        )
