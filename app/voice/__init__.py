"""Voice chat + voiceprint recognition (optional, lazy-loaded).

This package is only imported when a voice request actually arrives, so the
heavy speech dependencies (faster-whisper / resemblyzer / torch) never load in
text-only mode.
"""
