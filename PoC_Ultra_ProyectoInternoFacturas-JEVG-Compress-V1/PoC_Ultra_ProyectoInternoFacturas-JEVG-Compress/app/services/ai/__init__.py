from app.core.config import settings
from app.services.ai.base import DocumentAnalyzer
from app.services.ai.content_understanding import AzureContentUnderstandingAnalyzer
from app.services.ai.document_intelligence import AzureDocumentIntelligenceAnalyzer
from app.services.ai.foundry import AzureFoundryAnalyzer
from app.services.ai.mock_analyzer import LocalMockAnalyzer


def get_document_analyzer() -> DocumentAnalyzer:
    provider = settings.document_ai_provider.lower()
    if not settings.ai_enabled or provider == "mock":
        return LocalMockAnalyzer()
    mapping = {
        "document_intelligence": AzureDocumentIntelligenceAnalyzer,
        "content_understanding": AzureContentUnderstandingAnalyzer,
        "foundry": AzureFoundryAnalyzer,
    }
    return mapping.get(provider, LocalMockAnalyzer)()


__all__ = ["get_document_analyzer", "DocumentAnalyzer"]
