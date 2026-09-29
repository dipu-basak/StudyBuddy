import flet as ft
from theme import (
    BG_COLOR, CARD_BG, CARD_BG_MUTED, INSET_BG, PRIMARY_TEAL, 
    PRIMARY_TEAL_DARK, PRIMARY_TEAL_LIGHT, PRIMARY_TEAL_BORDER,
    ACCENT_ORANGE, ACCENT_ORANGE_DARK, ACCENT_ORANGE_LIGHT, ACCENT_ORANGE_BORDER,
    TEXT_TITLE, TEXT_BODY, TEXT_MUTED, TEXT_LIGHT, BORDER_COLOR, 
    CARD_SHADOW, SOFT_SHADOW, soft_card, pill_tag
)

class DashboardView:
    def __init__(self, page: ft.Page, user_data: dict, on_logout):
        self.page = page
        self.user = user_data or {}
        self.on_logout = on_logout

        # ── State Variables ──────────────────────────────────────
        self.selected_mode = "both"  # "summary", "quiz", "both"
        self.upload_type = "file"    # "file", "text"
        self.active_nav = "Workspace"
        self.selected_file_name = None
        self.selected_file_size = None

        # File Picker setup (Flet 1.0+ service, not added to page.overlay to prevent Flutter control error)
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

        # Mode card references
        self.mode_summary_card = None
        self.mode_quiz_card = None
        self.mode_both_card = None

        # Upload type button references
        self.upload_doc_btn = None
        self.upload_paste_btn = None
        self.dropzone_container = None

    # ── Notification Helper (stays on dashboard) ────────────────
    def _notify(self, message: str, is_info: bool = True):
        snack = ft.SnackBar(
            content=ft.Row([
                ft.Icon(ft.Icons.CHECK_CIRCLE if is_info else ft.Icons.INFO_OUTLINE, color=ft.Colors.WHITE, size=18),
                ft.Text(message, color=ft.Colors.WHITE, size=13, weight=ft.FontWeight.W_500),
            ], spacing=10),
            bgcolor=PRIMARY_TEAL if is_info else ACCENT_ORANGE_DARK,
            behavior=ft.SnackBarBehavior.FLOATING,
            duration=2800,
        )
        self.page.overlay.append(snack)
        snack.open = True
        self.page.update()

    # ── Event Handlers ──────────────────────────────────────────
    def _apply_picked_file(self, name: str, size: int | float | None = None):
        self.selected_file_name = name
        size_mb = round(size / (1024 * 1024), 2) if size else 0.5
        self.selected_file_size = f"{size_mb} MB"
        self.file_status_text.value = f"Selected: {self.selected_file_name} ({self.selected_file_size}) ✓"
        self.file_status_text.visible = True
        self.file_status_text.color = PRIMARY_TEAL
        self._notify(f"Attached: {self.selected_file_name}")
        self.page.update()

    def _on_file_picked(self, e: ft.FilePickerResultEvent):
        if e.files and len(e.files) > 0:
            picked = e.files[0]
            self._apply_picked_file(picked.name, picked.size)
        else:
            self.selected_file_name = None
            self.file_status_text.visible = False
            self.page.update()

    async def _handle_browse_click(self, _):
        try:
            files = await self.file_picker.pick_files(
                dialog_title="Select Lecture Slides or Notes",
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["pdf", "png", "jpg", "jpeg", "txt"]
            )
            if files and len(files) > 0:
                self._apply_picked_file(files[0].name, files[0].size)
                return
        except Exception:
            pass

        # Native OS file dialog fallback
        try:
            import tkinter as tk
            from tkinter import filedialog
            import os
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            filepath = filedialog.askopenfilename(
                title="Select Lecture Slides or Notes",
                filetypes=[("Documents & Images", "*.pdf;*.png;*.jpg;*.jpeg;*.txt"), ("All Files", "*.*")]
            )
            root.destroy()
            if filepath:
                fname = os.path.basename(filepath)
                fsize = os.path.getsize(filepath)
                self._apply_picked_file(fname, fsize)
        except Exception:
            pass

    def _select_mode(self, mode: str):
        self.selected_mode = mode
        
        # Reset card styles
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

        # Update descriptive subtext
        if mode == "both":
            self.mode_subtext.value = "Displays the 30-min summary first, then seamlessly unlocks the 5-min timed quiz."
            self._notify("Selected Exam Prep Mode: Summary + 5-Min Timed Quiz")
        elif mode == "summary":
            self.mode_subtext.value = "Generates high-yield bullet point breakdowns, core formulas, and key definitions."
            self._notify("Selected Exam Prep Mode: Summary Only")
        elif mode == "quiz":
            self.mode_subtext.value = "Generates a 15-question blitz quiz with a 5-minute countdown timer to test recall."
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
            self._notify("Switched to File Upload mode (PDF, JPG, PNG)")
        else:
            self.upload_paste_btn.bgcolor = PRIMARY_TEAL_LIGHT
            self.upload_paste_btn.border = ft.Border.all(1.5, PRIMARY_TEAL)
            self.upload_doc_btn.bgcolor = CARD_BG
            self.upload_doc_btn.border = ft.Border.all(1, BORDER_COLOR)

            self.dropzone_container.visible = False
            self.notes_paste_input.visible = True
            self.notes_word_count.visible = True
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
        
        # Keep user strictly on the dashboard and provide dynamic responsive feedback
        if nav_name == "Workspace":
            self._notify("Active Workspace: StudyBlitz Prep Dashboard")
        elif nav_name == "History":
            self._notify("Recent History: 0 study sessions recorded yet. Upload notes to create one!")
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
                        ft.Row([ft.Icon(ft.Icons.CHECK, color=PRIMARY_TEAL, size=18), ft.Text("GPT-4o + Gemini 2.0 Flash reasoning", size=13, weight=ft.FontWeight.W_500)]),
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
                ft.FilledButton("Upgrade for $4.99/mo", bgcolor=ACCENT_ORANGE, color=ft.Colors.WHITE, on_click=lambda _: (close_dialog(_), self._notify("Pro Upgrade checkout will be connected in next phase."))),
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

    # ── Layout Builders ──────────────────────────────────────────
    def _build_navbar(self) -> ft.Container:
        user_name = self.user.get("name") or "Student"
        streak_val = self.user.get("streak", 0)
        xp_val = self.user.get("xp", 0)
        level_val = self.user.get("level", 1)
        requests_today = self.user.get("requests_today", 0)
        requests_left = max(0, 3 - requests_today)

        # Logo section
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
                pill_tag("Soft UI", bgcolor=INSET_BG, text_color=TEXT_MUTED),
            ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Text("30-Minute Summary & 5-Minute Timed Quiz", size=10, color=TEXT_MUTED),
        ], spacing=1)

        # Nav Buttons (Workspace, History, Achievements, Pro Upgrade)
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
                ft.Icon(ft.Icons.MILITARY_TECH_OUTLINED, size=15, color=TEXT_MUTED),
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

        # Right side stat pills (dynamic from user data)
        streak_pill = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.LOCAL_FIRE_DEPARTMENT, size=14, color=ACCENT_ORANGE_DARK),
                ft.Text(f"{streak_val}d", size=12, weight=ft.FontWeight.BOLD, color=ACCENT_ORANGE_DARK),
            ], spacing=4),
            padding=ft.Padding(10, 5, 10, 5),
            bgcolor=ACCENT_ORANGE_LIGHT,
            border_radius=20,
            border=ft.Border.all(1, ACCENT_ORANGE_BORDER),
            on_click=lambda _: self._notify(f"Current Login Streak: {streak_val} day(s). Complete daily quizzes to build streak!"),
        )

        xp_pill = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.EMOJI_EVENTS_OUTLINED, size=14, color="#B45309"),
                ft.Text(f"Lv.{level_val} • {xp_val} XP", size=12, weight=ft.FontWeight.W_600, color=TEXT_TITLE),
            ], spacing=4),
            padding=ft.Padding(10, 5, 10, 5),
            bgcolor=CARD_BG,
            border_radius=20,
            border=ft.Border.all(1, BORDER_COLOR),
            on_click=lambda _: self._notify(f"Experience: {xp_val} XP earned."),
        )

        quota_pill = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.AUTO_AWESOME, size=14, color=PRIMARY_TEAL),
                ft.Text(f"{requests_left}/3 Free", size=12, weight=ft.FontWeight.W_600, color=TEXT_TITLE),
            ], spacing=4),
            padding=ft.Padding(10, 5, 10, 5),
            bgcolor=CARD_BG,
            border_radius=20,
            border=ft.Border.all(1, BORDER_COLOR),
            on_click=lambda _: self._notify(f"Daily Free Quota: {requests_left} of 3 requests remaining today."),
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
                # Left brand & nav
                ft.Row([
                    logo_icon,
                    brand_col,
                    ft.Container(width=16),
                    self.nav_workspace_btn,
                    self.nav_history_btn,
                    self.nav_achievements_btn,
                    self.nav_pro_btn,
                ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),

                # Right stats & profile
                ft.Row([
                    streak_pill,
                    xp_pill,
                    quota_pill,
                    user_profile_pill,
                ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding(20, 12, 20, 12),
        )

    def _build_left_history_card(self) -> ft.Container:
        uploads_count = self.user.get("total_uploads", 0)

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
                    ft.Text(f"{uploads_count} sessions saved", size=10, color=TEXT_MUTED),
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
                on_click=lambda _: self._notify("Start New Session: Use the center workspace to upload notes."),
            ),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

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

        history_action_btn = ft.Container(
            content=ft.Text("View History →", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
            padding=ft.Padding(0, 10, 0, 10),
            bgcolor=PRIMARY_TEAL,
            border_radius=20,
            alignment=ft.Alignment(0, 0),
            on_click=lambda _: self._notify("History view: Your past summaries and quiz scores will be listed here."),
        )

        content = ft.Column([
            header,
            ft.Container(height=24),
            empty_illustration,
            ft.Container(height=24),
            history_action_btn,
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=0)

        return soft_card(content, width=240, padding=16, border_radius=18)

    def _build_center_workspace_card(self) -> ft.Container:
        # Dual AI badge
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

        # 3 Exam Prep Mode Cards
        self.mode_summary_card = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.MENU_BOOK_ROUNDED, size=15, color=PRIMARY_TEAL_DARK),
                ft.Text("Summary Only", size=12, weight=ft.FontWeight.W_600, color=TEXT_BODY),
            ], alignment=ft.MainAxisAlignment.CENTER, spacing=6),
            padding=ft.Padding(12, 10, 12, 10),
            bgcolor=CARD_BG,
            border_radius=12,
            border=ft.Border.all(1, BORDER_COLOR),
            expand=True,
            on_click=lambda _: self._select_mode("summary"),
        )

        self.mode_quiz_card = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.TIMER_OUTLINED, size=15, color=PRIMARY_TEAL_DARK),
                ft.Text("Quiz Only (5m)", size=12, weight=ft.FontWeight.W_600, color=TEXT_BODY),
            ], alignment=ft.MainAxisAlignment.CENTER, spacing=6),
            padding=ft.Padding(12, 10, 12, 10),
            bgcolor=CARD_BG,
            border_radius=12,
            border=ft.Border.all(1, BORDER_COLOR),
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
            bgcolor=PRIMARY_TEAL_LIGHT,  # Selected by default
            border_radius=12,
            border=ft.Border.all(1.5, PRIMARY_TEAL),
            expand=True,
            on_click=lambda _: self._select_mode("both"),
        )

        modes_row = ft.Row([
            self.mode_summary_card,
            self.mode_quiz_card,
            self.mode_both_card,
        ], spacing=10)

        # Upload Type Selector Pills
        self.upload_doc_btn = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.CLOUD_UPLOAD_OUTLINED, size=14, color=PRIMARY_TEAL_DARK),
                ft.Text("Upload Document / Image", size=12, weight=ft.FontWeight.W_600, color=TEXT_BODY),
            ], spacing=6),
            padding=ft.Padding(12, 6, 12, 6),
            bgcolor=PRIMARY_TEAL_LIGHT,
            border_radius=20,
            border=ft.Border.all(1.5, PRIMARY_TEAL),
            on_click=lambda _: self._select_upload_type("file"),
        )

        self.upload_paste_btn = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.NOTE_ADD_OUTLINED, size=14, color=TEXT_MUTED),
                ft.Text("Paste Notes / Text", size=12, weight=ft.FontWeight.W_600, color=TEXT_MUTED),
            ], spacing=6),
            padding=ft.Padding(12, 6, 12, 6),
            bgcolor=CARD_BG,
            border_radius=20,
            border=ft.Border.all(1, BORDER_COLOR),
            on_click=lambda _: self._select_upload_type("text"),
        )

        upload_type_row = ft.Row([
            self.upload_doc_btn,
            self.upload_paste_btn,
        ], spacing=8)

        # Quick Test Chips
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
                on_click=lambda _: self._apply_quick_topic("Computer Science: Big-O Notation & Binary Search Trees"),
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

        # Subject Input Label
        subject_label = ft.Text("Subject or Exam Topic (Optional)", size=11, weight=ft.FontWeight.W_600, color=TEXT_MUTED)

        # Drag and Drop Inset Area
        browse_btn = ft.Container(
            content=ft.Text("Browse Files", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
            padding=ft.Padding(20, 8, 20, 8),
            bgcolor=PRIMARY_TEAL,
            border_radius=20,
            action=ft.PickFiles(
                self.file_picker,
                dialog_title="Select Lecture Slides or Notes",
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["pdf", "png", "jpg", "jpeg", "txt"]
            ),
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
            action=ft.PickFiles(
                self.file_picker,
                dialog_title="Select Lecture Slides or Notes",
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["pdf", "png", "jpg", "jpeg", "txt"]
            ),
            on_click=self._handle_browse_click,
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
            self.dropzone_container,
        ], spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)

        return soft_card(content, width=640, padding=24, border_radius=22)

    def _build_right_achievements_card(self) -> ft.Container:
        streak_val = self.user.get("streak", 0)
        xp_val = self.user.get("xp", 0)
        level_val = self.user.get("level", 1)
        uploads_count = self.user.get("total_uploads", 0)
        best_score = self.user.get("best_quiz_score", 0.0)
        best_score_str = f"{int(best_score)}%" if best_score > 0 else "--"

        # Level title mapping
        level_titles = {
            1: "Newcomer",
            2: "Student",
            3: "Learner",
            4: "Scholar",
            5: "Expert",
            6: "Academic Legend"
        }
        level_title = level_titles.get(level_val, "Newcomer")

        # XP Progress calculation
        if level_val == 1:
            progress_val = min(1.0, xp_val / 200.0) if xp_val > 0 else 0.0
            next_level_text = f"{int(progress_val * 100)}% to Lv.2"
        elif level_val == 2:
            progress_val = min(1.0, (xp_val - 200) / 300.0) if xp_val > 200 else 0.0
            next_level_text = f"{int(progress_val * 100)}% to Lv.3"
        else:
            progress_val = min(1.0, (xp_val - 500) / 500.0) if xp_val > 500 else 0.0
            next_level_text = f"{int(progress_val * 100)}% to Lv.{level_val + 1}"

        # Badges calculation
        badges_list = self.user.get("badges", [])
        badges_count = len(badges_list)
        badges_pct = int((badges_count / 6.0) * 100)

        # Header
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

        # Total Experience section
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

        # Badges section
        badges_header = ft.Row([
            ft.Text(f"BADGES ({badges_count}/6)", size=10, weight=ft.FontWeight.BOLD, color=TEXT_MUTED),
            ft.Text(f"{badges_pct}% Complete", size=10, weight=ft.FontWeight.BOLD, color=PRIMARY_TEAL),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        # 4 Badge Cards
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

        # Two Stat Boxes
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

        # Bottom Button
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

    # ── Main Render ──────────────────────────────────────────────
    def render(self) -> ft.Control:
        navbar = self._build_navbar()
        left_col = self._build_left_history_card()
        center_col = self._build_center_workspace_card()
        right_col = self._build_right_achievements_card()

        main_content_row = ft.Row([
            left_col,
            center_col,
            right_col,
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
