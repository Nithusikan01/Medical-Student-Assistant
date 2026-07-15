from uuid import uuid4
from pathlib import Path

from docling.document_converter import DocumentConverter

from .base_parser import BaseParser
from .schemas import ParsedDocument, ParsedElement


class DoclingParser(BaseParser):

    def __init__(self):

        self.converter = DocumentConverter()

    def parse(self, filepath: Path | str):

        result = self.converter.convert(Path(filepath))

        document = result.document

        markdown = document.export_to_markdown()

        element = ParsedElement(
            id=str(uuid4()),
            type="markdown",
            text=markdown
        )

        return ParsedDocument(
            filename=Path(filepath).name,
            parser="docling",
            elements=[element]
        )