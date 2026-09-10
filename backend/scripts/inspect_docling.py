from inspect import signature
from docling.document_converter import DocumentConverter

print(signature(DocumentConverter.convert_all))

help(DocumentConverter.convert_all)