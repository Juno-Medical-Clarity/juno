from abc import ABC, abstractmethod


class SimplifyPipeline(ABC):
    @abstractmethod
    def run(self, text: str) -> dict:
        pass
