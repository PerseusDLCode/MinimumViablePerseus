from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Generic, TypeVar

if TYPE_CHECKING:
    from mvp.document import TEIDocument

T = TypeVar("T")


class Compiler(ABC, Generic[T]):
    """Abstract base for pipeline compilers.

    Each concrete compiler transforms a source of type T into artifacts
    written under output_path.  Failures are signalled with CompilationError.
    """

    @abstractmethod
    def compile(self, source: T, output_path: Path, **kwargs) -> None:
        """Compile source into artifacts written under output_path.

        Raises:
            CompilationError: on failure.
        """
        ...


class CompilationError(Exception):
    """Raised when a compiler fails to produce its artifact.

    Carries enough context for the BuildPipeline to log clearly
    and decide whether to continue or abort.
    """

    def __init__(
        self,
        document: TEIDocument,
        message: str,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.document = document
        self.message = message
        self.cause = cause

    def __str__(self) -> str:
        base = f"Compilation failed for {self.document.path}: {self.args[0]}"
        if self.cause:
            base += f" (caused by: {self.cause})"
        return base
