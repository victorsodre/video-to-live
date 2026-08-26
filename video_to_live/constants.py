"""Fixed output recipe that already animated on an iPhone lock screen (2026-08-20)."""

WIDTH = 1080
HEIGHT = 1920
FPS = 60
DURATION = 1.0
FRAME_COUNT = 60
TIMESCALE = 600
CRF = 20

CONTENT_IDENTIFIER_KEY = "com.apple.quicktime.content.identifier"
LIVE_PHOTO_AUTO_KEY = "com.apple.quicktime.live-photo.auto"
VITALITY_SCORE_KEY = "com.apple.quicktime.live-photo.vitality-score"
VITALITY_VERSION_KEY = "com.apple.quicktime.live-photo.vitality-scoring-version"
STILL_IMAGE_TIME_KEY = "com.apple.quicktime.still-image-time"
VIDEO_ORIENTATION_KEY = "com.apple.quicktime.video-orientation"

# 1 frame at 60 fps, in the 600 Hz movie timescale.
STILL_MARKER_TICKS = TIMESCALE // FPS
# Cover frame in the middle of the 1 s clip.
STILL_TIME_SECONDS = DURATION / 2.0
