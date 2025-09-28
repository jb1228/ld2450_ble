from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LD2450BLEState:

    target_1_x: int = 0
    target_1_y: int = 0
    target_1_speed: int = 0
    target_1_resolution: int = 0
    
    target_2_x: int = 0
    target_2_y: int = 0
    target_2_speed: int = 0
    target_2_resolution: int = 0

    target_3_x: int = 0
    target_3_y: int = 0
    target_3_speed: int = 0
    target_3_resolution: int = 0

@dataclass(frozen=True)
class LD2450BLEConfig:
    
    target_mode: int = 0
    
    fw_ver: str = ""
    
    mac_addr: str = ""
    
    zone_type: int = 0
    zone_1_x1: int = 0
    zone_1_y1: int = 0
    zone_1_x2: int = 0
    zone_1_y2: int = 0
    zone_2_x1: int = 0
    zone_2_y1: int = 0
    zone_2_x2: int = 0
    zone_2_y2: int = 0
    zone_3_x1: int = 0
    zone_3_y1: int = 0
    zone_3_x2: int = 0
    zone_3_y2: int = 0