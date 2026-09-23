from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class DocumentAnalyzer(ABC):
    @abstractmethod
    def health_check(self) -> dict[str, Any]: ...

    @abstractmethod
    def analyze_document(self, path: Path) -> dict[str, Any]: ...

    @abstractmethod
    def extract_fields(self, path: Path, fields: list[str]) -> dict[str, Any]: ...

    @abstractmethod
    def semantic_compare(self, expected: str, detected: str) -> dict[str, Any]: ...

