"""Ingestion package exporting readers, batch manager, and pipeline."""
from app.ingestion.batch_manager import BatchManager, DuplicateFileError
from app.ingestion.csv_reader import (
    REQUIRED_COLUMNS,
    CSVReader,
    FileFormatError,
    compute_content_hash,
    compute_file_hash,
    load_csv,
)
from app.ingestion.json_reader import JSONFormatError, JSONReader
from app.ingestion.pipeline import (
    IngestionPipeline,
    PipelineExecutionResult,
    PipelineResult,
)

__all__ = [
    "REQUIRED_COLUMNS",
    "FileFormatError",
    "JSONFormatError",
    "DuplicateFileError",
    "CSVReader",
    "JSONReader",
    "load_csv",
    "compute_file_hash",
    "compute_content_hash",
    "BatchManager",
    "IngestionPipeline",
    "PipelineResult",
    "PipelineExecutionResult",
]
