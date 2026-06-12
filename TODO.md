# Dependency Removal TODO

- [x] Refactor `handlers/wake_word_manager.py` to remove `openwakeword` dependency and wakeword-model loop; keep VAD/listen-based capture.
- [x] Update `voice_assistant.py` messaging/comments to reflect VAD/listen-based activation (no wakeword dependency).
- [x] Update `README.md` to remove wakeword dependency claims and document VAD/listen-based behavior.
- [x] Validate syntax: `python -m py_compile handlers/wake_word_manager.py voice_assistant.py`.
- [x] Update this TODO with completion status.
