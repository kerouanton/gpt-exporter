# GPT Exporter characterization fixtures

These fixtures describe stable v2.8 behavior that must remain unchanged during the v2.9 packaging/refactoring work.

They are deliberately synthetic and contain no private archive data.

The initial fixture set focuses on deterministic, implementation-neutral contracts:

- cumulative conversation preservation: a shorter/equal incoming conversation must never replace a larger archived snapshot;
- larger incoming conversations are eligible for replacement;
- current-batch semantics contain only newly written or enlarged conversations;
- archive pipeline step order remains import → inventory → manifest → export → index;
- source bundles are retained on failure and deleted only after complete success.

Later fixtures may add assets, Markdown/DOCX semantic checks, audit classifications, and SQLite metadata preservation.
