# cli
- What: package command shell for `qf-data` and module execution.
- Why: converts operator input into calls to `data.api`.
- Keep: parsing, output formatting, and exit-code handling here.
- Avoid: dataset business logic or direct family/storage access outside `data.api`.
