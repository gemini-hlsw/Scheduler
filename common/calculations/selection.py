from dataclasses import dataclass
from typing import Mapping

from common.minimodel import ProgramID, Site
from .nightevents import NightEvents
from .programinfo import ProgramInfo


@dataclass(frozen=True)
class Selection:
    """
    The selection of information passed by the Selector to the Optimizer.
    This includes the list of programs that are schedulable and the night event for the nights under consideration.
    """
    program_info: Mapping[ProgramID, ProgramInfo]
    night_events: Mapping[Site, NightEvents]

    def __post_init__(self):
        object.__setattr__(self, 'program_ids', frozenset(self.program_info.keys()))
