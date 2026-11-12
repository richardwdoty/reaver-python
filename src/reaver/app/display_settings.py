# src/reaver/app/display_settings.py

from dataclasses import dataclass


@dataclass
class DisplaySettings:
    display_mode: str = "displayed_channels"
    selected_colors: tuple[bool, bool, bool] = (True, True, True)
    input_channel: str = "red"
    gamma_adjust: bool = False

    center_line_color: tuple[int, int, int] = (255, 255, 255)
    edge_line_color: tuple[int, int, int] = (0, 255, 0)