# Wake Word Performance + Text Check TODO

- [x] Update `handlers/wake_word_manager.py`:
  - [x] Add configurable transcription segment duration (1.0s)
  - [x] Use only last 1.0s audio for transcription after wakeword detection
  - [x] Harden text handling when transcription returns None/empty
  - [x] Optimize wakeword text check normalization
  - [x] Move wakeword variant list to class-level constant
- [ ] Run thorough validation:
  - [x] Syntax validation for updated file
  - [ ] Flow validation (detect -> transcribe -> text-check -> command path) — pending user runtime test
  - [ ] Edge-case validation (empty transcription / exceptions / repeated detections) — pending user runtime test
- [x] Summarize changes and test outcomes

## Exa Search Connector TODO
- [x] Review existing `connectors/search_engine.py` structure
- [x] Add `ExaSearch` connector class in `connectors/search_engine.py`
- [x] Add Exa key validation and client initialization
- [x] Implement `quick_search`, `search`, and `handle_search_action_with_feedback`
- [x] Update TODO progress after code changes
