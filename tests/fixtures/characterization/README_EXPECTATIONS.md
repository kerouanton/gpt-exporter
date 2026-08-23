# v2.8 characterization expectations

The characterization suite is intended to lock observable v2.8 behavior before internal refactoring begins.

Current invariants:

1. Conversation snapshots are compared by uncompressed JSON size.
2. A larger incoming conversation replaces the stored conversation.
3. An equal or smaller incoming conversation is preserved and does not rewrite the stored snapshot.
4. The per-run batch contains only conversations actually written during that import.
5. Invalid or missing source bundles fail before archive content is created.

These are behavioral contracts, not prescriptions for the v2.9 implementation.
