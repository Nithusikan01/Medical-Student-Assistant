import time
from pathlib import Path

from pypdf import PdfReader

from rag_application.ingestion_v2.docling_parser import DoclingParser


# ==============================================================================
# Configuration
# ==============================================================================

file_path = Path(
    "E:/Learning/RAG Applications/rag_application/data/raw/"
    "Ganongs Review of Medical Physiology 26th edition 2019_compressed.pdf"
)

BATCH_SIZE = 10

# ==============================================================================
# Initialize
# ==============================================================================

# parser = DoclingParser()

reader = PdfReader(file_path)
total_pages = len(reader.pages)

total_elements = 0
total_batches = 0

print(f"Processing '{file_path.name}'...")
print(f"Total pages : {total_pages}")
print(f"Batch size  : {BATCH_SIZE}")
print()

# ==============================================================================
# Benchmark
# ==============================================================================

overall_start = time.perf_counter()

for start_page in range(1, total_pages + 1, BATCH_SIZE):

    parser = DoclingParser()

    end_page = min(start_page + BATCH_SIZE - 1, total_pages)

    document = parser.parse(
        file_path,
        page_range=(start_page, end_page),
    )

    total_batches += 1
    total_elements += len(document.elements)

overall_end = time.perf_counter()

total_time = overall_end - overall_start

# ==============================================================================
# Results
# ==============================================================================

print("=" * 60)
print("BENCHMARK RESULTS")
print("=" * 60)
print(f"File               : {file_path.name}")
print(f"Total Pages        : {total_pages}")
print(f"Batch Size         : {BATCH_SIZE}")
print(f"Total Batches      : {total_batches}")
print(f"Total Elements     : {total_elements}")
print()
print(f"Total Time         : {total_time:.2f} seconds")
print(f"Average / Batch    : {total_time / total_batches:.2f} seconds")
print(f"Average / Page     : {total_time / total_pages:.2f} seconds")
print(f"Elements / Second  : {total_elements / total_time:.2f}")
print("=" * 60)