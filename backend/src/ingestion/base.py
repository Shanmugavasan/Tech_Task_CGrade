from abc import ABC, abstractmethod
from typing import AsyncGenerator
from src.core.models import EmailMessage

class BaseEmailSource(ABC):
    """Abstract interface for all email ingestion mechanisms."""
    
    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the data source and prepare the stream."""
        pass

    @abstractmethod
    async def stream_emails(self) -> AsyncGenerator[EmailMessage, None]:
        """Yields EmailMessage objects as they arrive chronologically."""
        pass