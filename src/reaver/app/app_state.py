# src/reaver/app/app_state.py

from dataclasses import dataclass, field
from pathlib import Path

from reaver.app.image_state import ReaverImageState
from reaver.app.params import SegmentationParams
from reaver.app.edit_state import EditState
from reaver.app.display_settings import DisplaySettings


@dataclass
class ReaverAppState:
    project_dir: Path | None = None
    image_states: dict[str, ReaverImageState] = field(default_factory=dict)
    active_image_id: str | None = None

    params: SegmentationParams = field(default_factory=SegmentationParams)
    edit_state: EditState = field(default_factory=EditState)
    display_settings: DisplaySettings = field(default_factory=DisplaySettings)

    pan_enabled: bool = False
    data_saving: bool = False

    @property
    def active_image(self) -> ReaverImageState | None:
        if self.active_image_id is None:
            return None
        return self.image_states[self.active_image_id]