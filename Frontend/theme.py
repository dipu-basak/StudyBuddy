import flet as ft

# ── Color Palette (Soft UI / StudyBuddy Theme) ───────────────
BG_COLOR = "#EEF3F8"               # Soft light gray/blue page background
CARD_BG = "#FFFFFF"                # Pure white card background
CARD_BG_MUTED = "#F8FAFC"          # Very light off-white
INSET_BG = "#F1F5F9"               # Inset dropzone / input background

PRIMARY_TEAL = "#0D9488"           # Brand teal for buttons, progress bar, active states
PRIMARY_TEAL_DARK = "#0F766E"      # Dark teal for text on light teal backgrounds
PRIMARY_TEAL_LIGHT = "#E6FFFA"     # Soft mint/teal for badge backgrounds
PRIMARY_TEAL_BORDER = "#99F6E4"    # Subtle teal border

ACCENT_ORANGE = "#F59E0B"          # Amber/Orange for streak, Pro Upgrade, Achievements CTA
ACCENT_ORANGE_DARK = "#D97706"     # Deep amber text
ACCENT_ORANGE_LIGHT = "#FEF3C7"    # Soft warm amber background
ACCENT_ORANGE_BORDER = "#FDE68A"

TEXT_TITLE = "#0F172A"             # Dark slate for large headings
TEXT_BODY = "#1E293B"              # Slate for primary text
TEXT_MUTED = "#64748B"             # Cool gray for subtitles & labels
TEXT_LIGHT = "#94A3B8"             # Light gray for placeholders

BORDER_COLOR = "#E2E8F0"           # Light gray card/input border
BORDER_ACTIVE = "#0D9488"          # Active teal border

# ── Shadows ──────────────────────────────────────────────────
CARD_SHADOW = ft.BoxShadow(
    spread_radius=0,
    blur_radius=16,
    color="#0D1E293B",
    offset=ft.Offset(0, 4),
)

SOFT_SHADOW = ft.BoxShadow(
    spread_radius=0,
    blur_radius=8,
    color="#08000000",
    offset=ft.Offset(0, 2),
)

INSET_SHADOW = ft.BoxShadow(
    spread_radius=0,
    blur_radius=6,
    color="#0A000000",
    offset=ft.Offset(0, 1),
)

# ── Helper Component Builders ─────────────────────────────────
def soft_card(content: ft.Control, width: int = None, padding: int = 20, border_radius: int = 18) -> ft.Container:
    """Creates a white rounded card with gentle elevation shadow matching the Soft UI mockup."""
    return ft.Container(
        content=content,
        width=width,
        padding=padding,
        bgcolor=CARD_BG,
        border_radius=border_radius,
        border=ft.Border.all(1, BORDER_COLOR),
        shadow=CARD_SHADOW,
    )

def pill_tag(text: str, icon: str = None, bgcolor: str = CARD_BG, text_color: str = TEXT_MUTED, border_color: str = BORDER_COLOR) -> ft.Container:
    """Creates a rounded pill badge."""
    controls = []
    if icon:
        controls.append(ft.Icon(icon, size=14, color=text_color))
    controls.append(ft.Text(text, size=12, weight=ft.FontWeight.W_600, color=text_color))
    
    return ft.Container(
        content=ft.Row(controls, spacing=5, alignment=ft.MainAxisAlignment.CENTER),
        padding=ft.Padding(12, 6, 12, 6),
        bgcolor=bgcolor,
        border_radius=20,
        border=ft.Border.all(1, border_color),
    )
