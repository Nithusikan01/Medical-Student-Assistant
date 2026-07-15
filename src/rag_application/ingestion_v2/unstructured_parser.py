from uuid import uuid4
from pathlib import Path

from unstructured.partition.auto import partition

from .base_parser import BaseParser
from .schemas import ParsedDocument
from .schemas import ParsedElement


class UnstructuredParser(BaseParser):

    def parse(self, filepath: Path | str):

        elements = partition(str(Path(filepath)))

        parsed = []

        for e in elements:

            parsed.append(

                ParsedElement(

                    id=str(uuid4()),

                    type=type(e).__name__,

                    text=e.text,

                    metadata={}

                )

            )

        return ParsedDocument(

            filename=Path(filepath).name,

            parser="unstructured",

            elements=parsed

        )