"""The suite's look, in one place (DOSSIER.md §10.3).

Semantic tokens: the colors and the stylesheet built from them. No
component writes raw hex; everything reads from here. The identity
is the workbench: dark warm charcoal surfaces, warm paper-white
text, and one bench-green accent, used only for primary actions
and focus — never for decoration.
"""

BACKGROUND = "#232019"      # dark warm charcoal
SURFACE = "#2c2822"         # cards, inputs
SURFACE_RAISED = "#35302a"  # buttons, hovered rows
SURFACE_HOVER = "#403a33"
BORDER = "#4a443a"
TEXT = "#f2ede3"            # warm paper-white
MUTED = "#b3aa99"
ACCENT = "#5aa75e"          # bench green: primary actions, focus
ACCENT_HOVER = "#6cb86f"
ACCENT_TEXT = "#14201a"     # dark text on the green button
ACCENT_DISABLED = "#3a4a3c"

CHAT_STYLESHEET = f"""
QWidget {{
    background: {BACKGROUND};
    color: {TEXT};
}}
QMenuBar {{
    background: {SURFACE};
    color: {TEXT};
}}
QMenuBar::item:selected {{
    background: {SURFACE_RAISED};
}}
QMenu {{
    background: {SURFACE};
    color: {TEXT};
    border: 1px solid {BORDER};
}}
QMenu::item:selected {{
    background: {SURFACE_RAISED};
}}
QPushButton {{
    background: {SURFACE_RAISED};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 6px 14px;
}}
QPushButton:hover {{
    background: {SURFACE_HOVER};
}}
QPushButton:pressed {{
    background: {SURFACE};
}}
QPushButton:disabled {{
    color: {MUTED};
}}
QPushButton#PrimaryButton {{
    background: {ACCENT};
    color: {ACCENT_TEXT};
    border: none;
    font-weight: bold;
}}
QPushButton#PrimaryButton:hover {{
    background: {ACCENT_HOVER};
}}
QPushButton#PrimaryButton:disabled {{
    background: {ACCENT_DISABLED};
    color: {MUTED};
}}
QLineEdit {{
    background: {SURFACE};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 6px 8px;
}}
QLineEdit:focus {{
    border: 1px solid {ACCENT};
}}
QLabel#RoleLabel {{
    color: {MUTED};
    font-family: monospace;
    font-size: 8pt;
}}
QLabel#MutedLabel {{
    color: {MUTED};
}}
QFrame#PlanCard {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 6px;
}}
QFrame#PlanCard QLabel {{
    background: transparent;
}}
QScrollArea {{
    border: none;
}}
QScrollBar:vertical {{
    background: {BACKGROUND};
    width: 12px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 4px;
    min-height: 20px;
}}
QProgressBar {{
    border: 1px solid {BORDER};
    border-radius: 4px;
    background: {SURFACE};
}}
QProgressBar::chunk {{
    background: {ACCENT};
}}
"""
