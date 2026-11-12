# src/reaver/app/params.py

from dataclasses import dataclass


@dataclass
class SegmentationParams:
    image_resolution: float = 1.0
    averaging_filter_size: int = 128
    grey_to_bw_threshold: float = 0.045
    min_connected_component_area: int = 1600

    conway_iterations: int = 8
    bridge_iterations: int = 1
    fill_iterations: int = 1
    bridge_fill_iterations: int = 4
    majority_iterations: int = 1
    thin_iterations: float = float("inf")

    vessel_thickness_threshold: float = 3.0
    wire_dilation_threshold: int = 0