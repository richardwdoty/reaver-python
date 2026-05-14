# src/reaver/app/edit_state.py

from dataclasses import dataclass


@dataclass
class EditState:
    brush_size: int = 1
    undo_enabled: bool = False
    previous_backup_state: bool = False
    is_dragging: bool = False
    edit_mode: str = "add"