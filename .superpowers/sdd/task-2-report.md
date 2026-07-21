# Task 2 Report: 从 IDML 提取字符和样式

## STATUS: DONE

## What was implemented

Added to `inject.py`:

- **`extract_from_idml(idml_path)`** -- Opens IDML as zip, reads `designmap.xml` for story order, then reads each Story XML, extracts paragraphs/characters/style info.
- **`_parse_story_order(designmap_xml)`** -- Extracts StoryList attribute from designmap.xml.
- **`_parse_story_xml(story_xml, story_idx)`** -- Parses a Story XML into ParagraphStyleRange blocks.
- **`_parse_paragraph_style_range(psr_xml, story_idx, para_idx)`** -- Extracts individual character records with style info from a PSR XML block.
- **`_get_story_header(story_xml)`** -- Returns XML content before the first ParagraphStyleRange.
- **`_get_story_footer(story_xml)`** -- Returns XML content after the last ParagraphStyleRange.

## Test Results

Test command:
```
python -c "
from inject import extract_from_idml
stories = extract_from_idml('275导出.idml')
total_chars = 0
total_punct = 0
for s in stories:
    for p in s['paragraphs']:
        for c in p['chars']:
            total_chars += 1
            if c['is_punct']:
                total_punct += 1
print(f'总字符记录数: {total_chars}')
print(f'其中旧标点数: {total_punct}')
"
```

Output:
```
总字符记录数: 6835
其中旧标点数: 971
```

Additional verification:
- 27 stories extracted, 34 paragraphs total
- Main text story (u15de): 8 paragraphs, 6,749 char records, 971 old punctuation marks
- 6 `<?ACE 18?>` special instructions correctly identified (is_special=True, style=None)
- 40 distinct style templates in the main content paragraph
- xml_header captures XML prolog + opening Story tags (548 chars for u15de)
- xml_footer captures closing tags (26 chars: `\n\t</Story>\n</idPkg:Story>\n`)
- Style templates correctly replace `<Content>...</Content>` with `{content}` using full-CSR offset calculation

## Bugfix relative to brief

The brief's code had an offset calculation bug in `_parse_paragraph_style_range`:
- `content_match.start()` was computed relative to `inner` (group 2)
- Then used as an index into `match.group(0)` (the full CSR XML)
- This would produce incorrect style templates

Fix: Re-search for `<Content>` in the full `match.group(0)` so offsets are consistent.

## Concerns

None. The function is ready for downstream use by Task 3+ (extract_from_result, validate_and_align, generate_idml).
