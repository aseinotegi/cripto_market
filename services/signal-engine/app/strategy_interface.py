from abc import ABC, abstractmethod
from typing import List, Optional
from common.schemas import FeatureVectorEvent, SignalEvent

class Strategy(ABC):
    def __init__(self, strategy_id: str):
        self.strategy_id = strategy_id

    @abstractmethod
    def on_features(self, event: FeatureVectorEvent) -> List[SignalEvent]:
        """
        Process a new feature vector and return a list of signals (if any).
        """
        pass
