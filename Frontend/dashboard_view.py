import asyncio
import os
import re
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
        self.quiz_timer_seconds = 300    # 5 minutes
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
        self.center_card_container.content = self._build_center_workspace_card()
        self.page.update()

    def _show_summary_view(self):
        """Switches center card to display the 30-minute exam summary."""
        self._stop_quiz_timer()
        self.center_mode = "summary"
        self.center_card_container.content = self._build_summary_card()
        self.page.update()

    async def _start_quiz_session(self):
        """Initializes and displays the 5-minute timed practice quiz."""
        if not self.current_session or not self.current_session.get("quiz"):
            self._notify("No quiz questions available for this study session.", is_info=False)
            return

        self.center_mode = "quiz"
        self.quiz_current_index = 0
        self.quiz_selected_answers = {}
        self.quiz_timer_seconds = 300  # 5 minutes
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
        pct = max(0.0, min(1.0, self.quiz_timer_seconds / 300.0))

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
        time_taken = max(1, 300 - self.quiz_timer_seconds)

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

        if self.streak_pill_text:
            self.streak_pill_text.value = f"{streak_val}d"
        if self.xp_pill_text:
            self.xp_pill_text.value = f"Lv.{level_val} • {xp_val} XP"
        if self.quota_pill_text:
            self.quota_pill_text.value = f"{requests_left}/3 Free"

        # Re-render sidebars
        self.left_history_container.content = self._build_left_history_card_content()
        self.right_achievements_container.content = self._build_right_achievements_card_content()
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

        if mode == "both":
            self.mode_subtext.value = "Displays the 30-min summary first, then seamlessly unlocks the 5-min timed quiz."
            self._notify("Selected Exam Prep Mode: Summary + 5-Min Timed Quiz")
        elif mode == "summary":
            self.mode_subtext.value = "Generates high-yield bullet point breakdowns, core formulas, and key definitions."
            self._notify("Selected Exam Prep Mode: Summary Only")
        elif mode == "quiz":
            self.mode_subtext.value = "Generates a timed practice quiz with a 5-minute countdown timer to test recall."
            self._notify("Selected Exam Prep Mode: Quiz Only (5m)")
        self.page.update()

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

    def _on_nav_clicked(self, nav_name: str):
        self.active_nav = nav_name
        if nav_name == "Workspace":
            self._show_workspace_view()
            self._notify("Active Workspace: StudyBuddy Prep Dashboard")
        elif nav_name == "History":
            if self.history_items:
                self._notify(f"Recent History: {len(self.history_items)} study session(s) saved in this session.")
            else:
                self._notify("Recent History: No study sessions recorded yet. Upload notes to create one!")
        elif nav_name == "Achievements":
            streak_val = self.user.get("streak", 0)
            xp_val = self.user.get("xp", 0)
            level_val = self.user.get("level", 1)
            self._notify(f"Achievements: Level {level_val} • {xp_val} XP • {streak_val}d Streak")
        elif nav_name == "Pro Upgrade":
            self._show_pro_modal()

    def _show_pro_modal(self):
        """Displays Pro Upgrade feature preview dialog without leaving the dashboard."""
        def close_dialog(_):
            dialog.open = False
            self.page.update()

        dialog = ft.AlertDialog(
            title=ft.Row([
                ft.Icon(ft.Icons.AUTO_AWESOME, color=ACCENT_ORANGE, size=24),
                ft.Text("StudyBuddy Pro Upgrade", size=18, weight=ft.FontWeight.BOLD, color=TEXT_TITLE),
            ], spacing=8),
            content=ft.Column([
                ft.Text("Unlock unlimited exam preps and premium AI reasoning:", size=13, color=TEXT_MUTED),
                ft.Container(
                    content=ft.Column([
                        ft.Row([ft.Icon(ft.Icons.CHECK, color=PRIMARY_TEAL, size=18), ft.Text("30 requests / 24 hours (vs 3 free)", size=13, weight=ft.FontWeight.W_500)]),
                        ft.Row([ft.Icon(ft.Icons.CHECK, color=PRIMARY_TEAL, size=18), ft.Text("GPT-4o + Gemini 3.5 Flash reasoning", size=13, weight=ft.FontWeight.W_500)]),
                        ft.Row([ft.Icon(ft.Icons.CHECK, color=PRIMARY_TEAL, size=18), ft.Text("Export study guides to PDF", size=13, weight=ft.FontWeight.W_500)]),
                        ft.Row([ft.Icon(ft.Icons.CHECK, color=PRIMARY_TEAL, size=18), ft.Text("Detailed quiz mistake breakdown", size=13, weight=ft.FontWeight.W_500)]),
                    ], spacing=10),
                    padding=16,
                    bgcolor=CARD_BG_MUTED,
                    border_radius=12,
                    border=ft.Border.all(1, BORDER_COLOR),
                ),
            ], tight=True, spacing=14),
            actions=[
                ft.TextButton("Maybe Later", on_click=close_dialog),
                ft.FilledButton("Upgrade for ৳499/mo", bgcolor=ACCENT_ORANGE, color=ft.Colors.WHITE, on_click=lambda _: (close_dialog(_), self._notify("Pro Upgrade checkout will be connected in next phase."))),
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
        self.nav_workspace_btn = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.DASHBOARD_ROUNDED, size=15, color=PRIMARY_TEAL),
                ft.Text("Workspace", size=12, weight=ft.FontWeight.BOLD, color=TEXT_TITLE),
            ], spacing=6),
            padding=ft.Padding(12, 6, 12, 6),
            bgcolor=CARD_BG,
            border_radius=20,
            border=ft.Border.all(1, BORDER_COLOR),
            shadow=SOFT_SHADOW,
            on_click=lambda _: self._on_nav_clicked("Workspace"),
        )

        self.nav_history_btn = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.HISTORY_ROUNDED, size=15, color=TEXT_MUTED),
                ft.Text("History", size=12, weight=ft.FontWeight.W_600, color=TEXT_MUTED),
            ], spacing=6),
            padding=ft.Padding(12, 6, 12, 6),
            bgcolor=CARD_BG,
            border_radius=20,
            border=ft.Border.all(1, BORDER_COLOR),
            on_click=lambda _: self._on_nav_clicked("History"),
        )

        self.nav_achievements_btn = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.EMOJI_EVENTS_OUTLINED, size=15, color=TEXT_MUTED),
                ft.Text("Achievements", size=12, weight=ft.FontWeight.W_600, color=TEXT_MUTED),
            ], spacing=6),
            padding=ft.Padding(12, 6, 12, 6),
            bgcolor=CARD_BG,
            border_radius=20,
            border=ft.Border.all(1, BORDER_COLOR),
            on_click=lambda _: self._on_nav_clicked("Achievements"),
        )

        self.nav_pro_btn = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.AUTO_AWESOME, size=14, color=ft.Colors.WHITE),
                ft.Text("Pro Upgrade", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
            ], spacing=5),
            padding=ft.Padding(14, 6, 14, 6),
            bgcolor=ACCENT_ORANGE,
            border_radius=20,
            shadow=ft.BoxShadow(spread_radius=0, blur_radius=8, color="#33F59E0B", offset=ft.Offset(0, 2)),
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

        self.quota_pill_text = ft.Text(f"{requests_left}/3 Free", size=12, weight=ft.FontWeight.W_600, color=TEXT_TITLE)
        quota_pill = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.AUTO_AWESOME, size=14, color=PRIMARY_TEAL),
                self.quota_pill_text,
            ], spacing=4),
            padding=ft.Padding(10, 5, 10, 5),
            bgcolor=CARD_BG,
            border_radius=20,
            border=ft.Border.all(1, BORDER_COLOR),
            on_click=lambda _: self._notify(f"Daily Free Quota: {max(0, 3 - self.user.get('requests_today', 0))} requests remaining today."),
        )

        user_profile_pill = ft.Container(
            content=ft.Row([
                ft.CircleAvatar(
                    content=ft.Text(user_name[0].upper(), size=12, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
                    radius=13,
                    bgcolor=PRIMARY_TEAL,
                ),
                ft.Text(user_name, size=13, weight=ft.FontWeight.W_600, color=TEXT_TITLE),
            ], spacing=6),
            padding=ft.Padding(8, 4, 12, 4),
            bgcolor=CARD_BG,
            border_radius=20,
            border=ft.Border.all(1, BORDER_COLOR),
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
                    self.nav_pro_btn,
                ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),

                ft.Row([
                    streak_pill,
                    xp_pill,
                    quota_pill,
                    user_profile_pill,
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
                ),
                ft.Column([
                    ft.Text("Recent History", size=13, weight=ft.FontWeight.BOLD, color=TEXT_TITLE),
                    ft.Text(f"{len(self.history_items)} session(s) active", size=10, color=TEXT_MUTED),
                ], spacing=0),
            ], spacing=8),

            ft.Container(
                content=ft.Icon(ft.Icons.ADD, size=14, color=TEXT_MUTED),
                width=24,
                height=24,
                border_radius=12,
                bgcolor=INSET_BG,
                alignment=ft.Alignment(0, 0),
                border=ft.Border.all(1, BORDER_COLOR),
                on_click=lambda _: self._show_workspace_view(),
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
                mode_label = item.get("mode", "both").capitalize()
                
                def _make_loader(rec):
                    return lambda _: self._load_history_item(rec)

                session_cards.append(
                    ft.Container(
                        content=ft.Row([
                            ft.Icon(ft.Icons.BOLT, size=16, color=PRIMARY_TEAL),
                            ft.Column([
                                ft.Text(topic_title[:20] + ("..." if len(topic_title) > 20 else ""), size=11, weight=ft.FontWeight.BOLD, color=TEXT_TITLE),
                                ft.Text(f"{mode_label} • Ready", size=9, color=TEXT_MUTED),
                            ], spacing=1, expand=True),
                            ft.Icon(ft.Icons.CHEVRON_RIGHT, size=14, color=TEXT_LIGHT),
                        ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        padding=ft.Padding(8, 8, 8, 8),
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

        history_action_btn = ft.Container(
            content=ft.Text("New Study Session +", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
            padding=ft.Padding(0, 10, 0, 10),
            bgcolor=PRIMARY_TEAL,
            border_radius=20,
            alignment=ft.Alignment(0, 0),
            on_click=lambda _: self._show_workspace_view(),
        )

        content = ft.Column([
            header,
            body_content,
            history_action_btn,
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

    # ── Right Sidebar (Achievements & Gamification) ─────────────
    def _build_right_achievements_card_content(self) -> ft.Control:
        streak_val = self.user.get("streak", 0)
        xp_val = self.user.get("xp", 0)
        level_val = 1 + (xp_val // 200)
        uploads_count = self.user.get("total_uploads", 0)
        best_score = self.user.get("best_quiz_score", 0.0)
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

        badges_list = self.user.get("badges", [])
        if xp_val >= 50 and "first" not in badges_list:
            badges_list.append("first")
        if best_score > 0 and "quiz" not in badges_list:
            badges_list.append("quiz")
        badges_count = len(badges_list)
        badges_pct = int((badges_count / 6.0) * 100)

        header = ft.Row([
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
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

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
            ft.Text(f"BADGES ({badges_count}/6)", size=10, weight=ft.FontWeight.BOLD, color=TEXT_MUTED),
            ft.Text(f"{badges_pct}% Complete", size=10, weight=ft.FontWeight.BOLD, color=PRIMARY_TEAL),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        def create_badge_item(slug: str, name: str) -> ft.Container:
            unlocked = slug in badges_list
            color = PRIMARY_TEAL if unlocked else TEXT_LIGHT
            bg = PRIMARY_TEAL_LIGHT if unlocked else CARD_BG
            border_c = PRIMARY_TEAL_BORDER if unlocked else BORDER_COLOR
            return ft.Container(
                content=ft.Column([
                    ft.Icon(ft.Icons.MILITARY_TECH, size=18, color=color),
                    ft.Text(name, size=10, weight=ft.FontWeight.W_600, color=color),
                ], spacing=2, alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                width=46,
                height=48,
                border_radius=10,
                bgcolor=bg,
                border=ft.Border.all(1, border_c),
                alignment=ft.Alignment(0, 0),
                on_click=lambda _: self._notify(f"Badge '{name}': {'Unlocked (+50 XP)' if unlocked else 'Locked (Complete study sessions to unlock)'}"),
            )

        badges_row = ft.Row([
            create_badge_item("first", "First"),
            create_badge_item("week", "Week"),
            create_badge_item("quiz", "Quiz"),
            create_badge_item("speed", "Speed"),
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
            on_click=lambda _: self._notify(f"Achievements: Level {level_val} {level_title} • {badges_count} of 6 badges earned."),
        )

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

        self.generate_session_btn = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.BOLT, color=ft.Colors.WHITE, size=18),
                ft.Text("Generate 30-Minute Study Guide", color=ft.Colors.WHITE, size=13, weight=ft.FontWeight.BOLD),
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
            ft.Container(height=8),
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
                    ft.Text("Back to Upload", size=12, weight=ft.FontWeight.BOLD, color=PRIMARY_TEAL),
                ], spacing=4),
                padding=ft.Padding(10, 5, 10, 5),
                bgcolor=PRIMARY_TEAL_LIGHT,
                border_radius=12,
                border=ft.Border.all(1, PRIMARY_TEAL_BORDER),
                on_click=lambda _: self._show_workspace_view(),
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

        self.quiz_progress_bar = ft.ProgressBar(
            value=max(0.0, min(1.0, self.quiz_timer_seconds / 300.0)),
            color=ACCENT_ORANGE_DARK if self.quiz_timer_seconds < 60 else PRIMARY_TEAL,
            bgcolor="#E2E8F0",
            height=6,
            border_radius=3,
        )

        header_row = ft.Row([
            ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.MENU_BOOK, size=13, color=PRIMARY_TEAL),
                    ft.Text("View Summary", size=11, weight=ft.FontWeight.BOLD, color=PRIMARY_TEAL),
                ], spacing=4),
                padding=ft.Padding(8, 4, 8, 4),
                bgcolor=PRIMARY_TEAL_LIGHT,
                border_radius=10,
                on_click=lambda _: self._show_summary_view(),
            ),
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
        action_row = ft.Row([
            ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.MENU_BOOK, color=PRIMARY_TEAL, size=16),
                    ft.Text("Review Summary", color=PRIMARY_TEAL, size=12, weight=ft.FontWeight.BOLD),
                ], spacing=6, alignment=ft.MainAxisAlignment.CENTER),
                bgcolor=CARD_BG,
                border=ft.Border.all(1.5, PRIMARY_TEAL),
                padding=ft.Padding(14, 10, 14, 10),
                border_radius=12,
                expand=True,
                alignment=ft.Alignment(0, 0),
                on_click=lambda _: self._show_summary_view(),
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

    # ── Main Render ──────────────────────────────────────────────
    def render(self) -> ft.Control:
        navbar = self._build_navbar()

        # Initialize sidebar and center containers
        self.left_history_container.content = self._build_left_history_card_content()
        self.right_achievements_container.content = self._build_right_achievements_card_content()
        self.center_card_container.content = self._build_center_workspace_card()

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
