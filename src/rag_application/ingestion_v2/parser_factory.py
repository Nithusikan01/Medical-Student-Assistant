from rag_application.ingestion_v2.docling_parser import DoclingParser
from rag_application.ingestion_v2.unstructured_parser import UnstructuredParser

class ParserFactory:

    _PARSERS = {
        "docling": DoclingParser,
        "unstructured": UnstructuredParser,
    }

    @classmethod
    def create(cls, name: str):
        try:
            return cls._PARSERS[name.lower()]()
        except KeyError:
            raise ValueError(f"Unknown parser: {name}")