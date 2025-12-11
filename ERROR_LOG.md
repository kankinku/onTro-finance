# Error Log & Lessons Learned

## 2025-12-12: Character Encoding Corruption in Data Files
- **Symptom**: CLI output showed `???` for Korean text in document snippets and domain entities.
- **Cause**: JSON files (`data/samples/sample_documents.json`, `data/domain/entities.json`) contained literal question marks `?` replacing Korean characters. This likely occurred during a previous file save operation where the encoding was not correctly set to UTF-8 or the environment defaulted to a non-Unicode page (e.g., CP1252/CP949) while writing characters unsupported by that encoding.
- **Resolution**: Manually restored the correct Korean text in the JSON files and ensured they were saved with UTF-8 encoding.
- **Prevention**: Always ensure `encoding='utf-8'` is specified when opening files for writing in Python (`open(..., 'w', encoding='utf-8')`). Verify JSON data integrity after batch updates.
