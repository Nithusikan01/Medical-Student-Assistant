from abc import ABC, abstractmethod
from pathlib import Path

from .schemas import ParsedDocument


class BaseParser(ABC):

    @abstractmethod
    def parse(self, filepath: Path | str) -> ParsedDocument:
        pass