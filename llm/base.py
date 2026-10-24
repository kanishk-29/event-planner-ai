"""Provider interface. The rest of the app only knows this, never a vendor SDK."""
from typing import Protocol, TypeVar
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMProvider(Protocol):
    def generate(self, system: str, user: str, schema: type[T]) -> T:
        """Return a validated instance of `schema` or raise."""
        ...
