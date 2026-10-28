import flet as ft
from api_client import api_client
from theme import (
    BG_COLOR, CARD_BG, INSET_BG, PRIMARY_TEAL, PRIMARY_TEAL_DARK, 
    PRIMARY_TEAL_LIGHT, TEXT_TITLE, TEXT_BODY, TEXT_MUTED, TEXT_LIGHT, 
    BORDER_COLOR, CARD_SHADOW, soft_card
)

class AuthView:
    def __init__(self, page: ft.Page, on_auth_success):
        self.page = page
        self.on_auth_success = on_auth_success
        self.is_signup = False  # False = Login, True = Sign Up

        # ── Form Inputs ──────────────────────────────────────────
        self.name_input = ft.TextField(
            label="Full Name",
            hint_text="Enter your full name",
            prefix_icon=ft.Icons.PERSON_OUTLINE,
            border_radius=12,
            bgcolor=INSET_BG,
            border_color=BORDER_COLOR,
            focused_border_color=PRIMARY_TEAL,
            text_size=14,
            visible=False,
            value="",
        )

        self.email_input = ft.TextField(
            label="Email Address",
            hint_text="Enter your email address",
            prefix_icon=ft.Icons.EMAIL_OUTLINED,
            border_radius=12,
            bgcolor=INSET_BG,
            border_color=BORDER_COLOR,
            focused_border_color=PRIMARY_TEAL,
            text_size=14,
            value="",
        )

        self.password_input = ft.TextField(
            label="Password",
            hint_text="Enter your password",
            prefix_icon=ft.Icons.LOCK_OUTLINE,
            password=True,
            can_reveal_password=True,
            border_radius=12,
            bgcolor=INSET_BG,
            border_color=BORDER_COLOR,
            focused_border_color=PRIMARY_TEAL,
            text_size=14,
            value="",
        )

        self.confirm_password_input = ft.TextField(
            label="Confirm Password",
            hint_text="Re-enter your password",
            prefix_icon=ft.Icons.LOCK_RESET,
            password=True,
            can_reveal_password=True,
            border_radius=12,
            bgcolor=INSET_BG,
            border_color=BORDER_COLOR,
            focused_border_color=PRIMARY_TEAL,
            text_size=14,
            visible=False,
            value="",
        )

        # ── Status / Error Banner ────────────────────────────────
        self.status_text = ft.Text("", size=13, weight=ft.FontWeight.W_500, color=ft.Colors.RED_600)
        self.status_container = ft.Container(
            content=self.status_text,
            padding=ft.Padding(12, 8, 12, 8),
            border_radius=10,
            bgcolor="#FEF2F2",
            border=ft.Border.all(1, "#FECACA"),
            visible=False,
        )

        # ── Loading Spinner ──────────────────────────────────────
        self.spinner = ft.ProgressRing(width=18, height=18, stroke_width=2.5, color=ft.Colors.WHITE, visible=False)
        self.submit_btn_text = ft.Text("Log In →", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE)

        self.submit_button = ft.Container(
            content=ft.Row([self.spinner, self.submit_btn_text], alignment=ft.MainAxisAlignment.CENTER, spacing=10),
            padding=ft.Padding(0, 12, 0, 12),
            bgcolor=PRIMARY_TEAL,
            border_radius=22,
            alignment=ft.Alignment(0, 0),
            on_click=self._handle_submit,
            animate=ft.Animation(150, ft.AnimationCurve.EASE_OUT),
        )

        # ── Tab Switch Buttons ───────────────────────────────────
        self.login_tab = ft.Container(
            content=ft.Text("Log In", size=14, weight=ft.FontWeight.BOLD, color=PRIMARY_TEAL),
            padding=ft.Padding(20, 8, 20, 8),
            border_radius=20,
            bgcolor=PRIMARY_TEAL_LIGHT,
            border=ft.Border.all(1, PRIMARY_TEAL),
            on_click=lambda _: self._toggle_mode(False),
        )

        self.signup_tab = ft.Container(
            content=ft.Text("Sign Up", size=14, weight=ft.FontWeight.W_600, color=TEXT_MUTED),
            padding=ft.Padding(20, 8, 20, 8),
            border_radius=20,
            bgcolor=CARD_BG,
            border=ft.Border.all(1, BORDER_COLOR),
            on_click=lambda _: self._toggle_mode(True),
        )

    def _toggle_mode(self, is_signup: bool):
        self.is_signup = is_signup
        self.status_container.visible = False
        self.email_input.value = ""
        self.password_input.value = ""
        
        if is_signup:
            self.login_tab.bgcolor = CARD_BG
            self.login_tab.border = ft.Border.all(1, BORDER_COLOR)
            self.login_tab.content.color = TEXT_MUTED
            self.login_tab.content.weight = ft.FontWeight.W_600

            self.signup_tab.bgcolor = PRIMARY_TEAL_LIGHT
            self.signup_tab.border = ft.Border.all(1, PRIMARY_TEAL)
            self.signup_tab.content.color = PRIMARY_TEAL
            self.signup_tab.content.weight = ft.FontWeight.BOLD

            self.name_input.visible = True
            self.confirm_password_input.visible = True
            self.submit_btn_text.value = "Create Account →"
            self.name_input.value = ""
            self.confirm_password_input.value = ""
        else:
            self.signup_tab.bgcolor = CARD_BG
            self.signup_tab.border = ft.Border.all(1, BORDER_COLOR)
            self.signup_tab.content.color = TEXT_MUTED
            self.signup_tab.content.weight = ft.FontWeight.W_600

            self.login_tab.bgcolor = PRIMARY_TEAL_LIGHT
            self.login_tab.border = ft.Border.all(1, PRIMARY_TEAL)
            self.login_tab.content.color = PRIMARY_TEAL
            self.login_tab.content.weight = ft.FontWeight.BOLD

            self.name_input.visible = False
            self.confirm_password_input.visible = False
            self.submit_btn_text.value = "Log In →"

        self.page.update()

    def _show_error(self, message: str):
        self.status_text.value = message
        self.status_container.visible = True
        self.spinner.visible = False
        self.submit_button.opacity = 1.0
        self.page.update()

    async def _handle_submit(self, _):
        self.status_container.visible = False
        email = self.email_input.value.strip()
        password = self.password_input.value

        if not email or "@" not in email:
            self._show_error("Please enter a valid email address.")
            return

        if not password or len(password) < 6:
            self._show_error("Password must be at least 6 characters.")
            return

        if self.is_signup:
            name = self.name_input.value.strip()
            confirm = self.confirm_password_input.value
            if not name:
                self._show_error("Please enter your full name.")
                return
            if password != confirm:
                self._show_error("Passwords do not match.")
                return

            # Show loading
            self.spinner.visible = True
            self.page.update()

            success, msg, user_data, token = await api_client.signup(name, email, password)
        else:
            # Show loading
            self.spinner.visible = True
            self.page.update()

            success, msg, user_data, token = await api_client.login(email, password)

        self.spinner.visible = False

        if success:
            # Trigger dashboard transition callback
            await self.on_auth_success(user_data, token)
        else:
            self._show_error(msg)

    def render(self) -> ft.Control:
        header = ft.Column([
            ft.Row([
                ft.Container(
                    content=ft.Icon(ft.Icons.BOLT, color=ft.Colors.WHITE, size=24),
                    width=42,
                    height=42,
                    border_radius=21,
                    bgcolor=PRIMARY_TEAL,
                    alignment=ft.Alignment(0, 0),
                ),
                ft.Column([
                    ft.Row([
                        ft.Text("StudyBuddy", size=22, weight=ft.FontWeight.BOLD, color=TEXT_TITLE),
                    ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Text("30-Minute Summary & 5-Minute Timed Quiz", size=11, color=TEXT_MUTED),
                ], spacing=1),
            ], alignment=ft.MainAxisAlignment.CENTER, spacing=12),
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=6)

        tab_row = ft.Row([
            self.login_tab,
            self.signup_tab,
        ], alignment=ft.MainAxisAlignment.CENTER, spacing=10)

        card_content = ft.Column([
            header,
            ft.Divider(height=1, color=BORDER_COLOR),
            tab_row,
            self.status_container,
            self.name_input,
            self.email_input,
            self.password_input,
            self.confirm_password_input,
            self.submit_button,
        ], spacing=16, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)

        auth_card = soft_card(card_content, width=440, padding=32, border_radius=22)

        return ft.Container(
            content=ft.Column([
                auth_card,
                # ft.Text("FastAPI + Flet + MongoDB Authentication", size=12, color=TEXT_LIGHT),
            ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=16),
            alignment=ft.Alignment(0, 0),
            expand=True,
            bgcolor=BG_COLOR,
            padding=20,
        )
