# OCR and Table Parser Feature Track

## Status

This is a parallel feature track and is not part of the deployment-readiness critical path.

Current implementation status:

- OCR engine hook is implemented through a local `tesseract` CLI path for pages with `ocr_required=true` and embedded page images.
- True table parser is implemented for machine-readable text tables with header/cell grid extraction.
- Image-based or OCR-derived complex table reconstruction is still not implemented.

## OCR Scope

- Target only scanned PDF pages that currently surface `ocr_required=true`
- Extract plain text for downstream fragment processing
- Must preserve page number and document identity

## OCR Non-goals

- Handwriting recognition
- Form understanding
- Full layout intelligence
- Multimodal chart interpretation

## Table Parser Scope

- Target simple machine-readable tables in PDF text output
- Preserve caption, row count, column count, and basic cell grid structure
- Feed parsed table rows into future fragment/evidence extraction

## Table Parser Non-goals

- Image-only table extraction
- Financial spreadsheet formula interpretation
- Complex merged-cell layout fidelity

## Integration Points

- `main.py` PDF block extraction
- `src/extraction/fragment_extractor.py` block classification
- `src/extraction/pipeline.py` citation and block metadata propagation
- `src/web/operations_console.py` document structure inspection
