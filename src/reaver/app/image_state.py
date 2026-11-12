# src/reaver/app/image_state.py

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from reaver.app.params import SegmentationParams


@dataclass
class BaseImage:
    path: Path
    data: np.ndarray | None = None
    x_size: int | None = None
    y_size: int | None = None
    n_channels: int | None = None


@dataclass
class DerivedLayers:
    selected_channels: np.ndarray | None = None
    gray: np.ndarray | None = None
    local_mean: np.ndarray | None = None
    gray_neighbors: np.ndarray | None = None
    bw_1: np.ndarray | None = None
    bw_1_neighbors: np.ndarray | None = None
    bw_2: np.ndarray | None = None
    wire: np.ndarray | None = None
    dilated_wire: np.ndarray | None = None
    dilated_wire_2: np.ndarray | None = None
    branchpoints: np.ndarray | None = None
    endpoints: np.ndarray | None = None


@dataclass
class ReaverImageState:
    image_id: str
    path: Path

    base_image: BaseImage | None = None
    derived_layers: DerivedLayers = field(default_factory=DerivedLayers)

    image_loaded: bool = False
    image_segmented: bool = False
    wire_update_pending: bool = False
    input_channels: tuple[int, ...] = (0,)
    segmented_channels: tuple[int, ...] | None = None
    verified: bool = False
    dirty: bool = False

    metrics: dict[str, float] = field(default_factory=dict)
    measurements: dict[str, float] = field(default_factory=dict)
    edit_history: list = field(default_factory=list)
    undo_layers: DerivedLayers | None = None
    undo_available: bool = False
    edit_backup_locked: bool = False
    analysis_path: Path | None = None
    save_path: Path | None = None
    params: SegmentationParams | None = None
    proposed_params: SegmentationParams | None = None
