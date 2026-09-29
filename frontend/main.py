import os
import sys
import flet as ft

# Ensure current directory is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from auth_view import AuthView
from dashboard_view import DashboardView
from theme import BG_COLOR, PRIMARY_TEAL

def main(page: ft.Page):
    page.title = "StudyBuddy — 30-Minute Summary & 5-Minute Timed Quiz"
    page.bgcolor = BG_COLOR
    page.padding = 0
    page.theme_mode = ft.ThemeMode.LIGHT
    page.theme = ft.Theme(color_scheme_seed=PRIMARY_TEAL)

    current_user = None
    token = None

    def on_logout():
        nonlocal current_user, token
        current_user = None
        token = None
        show_auth_view()

    async def on_auth_success(user_data, jwt_token):
        nonlocal current_user, token
        current_user = user_data
        token = jwt_token
        show_dashboard_view()

    def show_auth_view():
        page.clean()
        auth_view = AuthView(page, on_auth_success=on_auth_success)
        page.add(auth_view.render())
        page.update()

    def show_dashboard_view():
        page.clean()
        dashboard_view = DashboardView(page, current_user, on_logout=on_logout)
        page.add(dashboard_view.render())
        page.update()

    # Initially render the Auth View
    show_auth_view()

if __name__ == "__main__":
    ft.run(main)
