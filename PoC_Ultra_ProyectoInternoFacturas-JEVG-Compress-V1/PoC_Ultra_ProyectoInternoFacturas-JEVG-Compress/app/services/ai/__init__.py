from app.core.config import settings
from app.services.ai.base import AnalyzerUnavailable, DocumentAnalyzer, InvoiceReading
from app.services.ai.content_understanding import AzureContentUnderstandingAnalyzer
from app.services.ai.document_intelligence import AzureDocumentIntelligenceAnalyzer
from app.services.ai.mock_analyzer import LocalMockAnalyzer
from app.services.ai.openai_analyzer import OpenAIInvoiceAnalyzer
from app.services.ai.pipeline import DocumentIntelligenceOpenAIAnalyzer

PROVIDERS = {
    "document_intelligence": AzureDocumentIntelligenceAnalyzer,
    "openai": OpenAIInvoiceAnalyzer,
    "foundry": OpenAIInvoiceAnalyzer,  # nombre anterior del analizador de OpenAI
    "document_intelligence_openai": DocumentIntelligenceOpenAIAnalyzer,
    "content_understanding": AzureContentUnderstandingAnalyzer,
}


def get_document_analyzer() -> DocumentAnalyzer:
    provider = settings.document_ai_provider.lower()
    if not settings.ai_enabled or provider == "mock":
        return LocalMockAnalyzer()
    return PROVIDERS.get(provider, LocalMockAnalyzer)()


__all__ = ["get_document_analyzer", "AnalyzerUnavailable", "DocumentAnalyzer", "InvoiceReading", "PROVIDERS"]
