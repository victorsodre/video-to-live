"""Lock-screen recipe that already animated on an iPhone (2026-08-26)."""

WIDTH = 1080
HEIGHT = 1920
FPS = 60
FRAME_COUNT = 60
TIMESCALE = 600
CRF = 20

# ffmpeg still encodes 1 s / 60 fps; the muxer stretches the container to 1.05 s.
ENCODE_DURATION = 1.0
CONTAINER_DURATION = 1.05
MVHD_DURATION = 630  # 630 / 600 = 1.05 s
VIDEO_MDHD_DURATION = 620  # 59*10 + 30
VIDEO_STTS = ((59, 10), (1, 30))

CONTENT_IDENTIFIER_KEY = "com.apple.quicktime.content.identifier"
LIVE_PHOTO_AUTO_KEY = "com.apple.quicktime.live-photo.auto"
STILL_IMAGE_TIME_KEY = "com.apple.quicktime.still-image-time"
STILL_IMAGE_TRANSFORM_KEY = "com.apple.quicktime.live-photo-still-image-transform"
LIVE_PHOTO_INFO_KEY = "com.apple.quicktime.live-photo-info"
VITALITY_SCORE_KEY = "com.apple.quicktime.live-photo.vitality-score"
VITALITY_VERSION_KEY = "com.apple.quicktime.live-photo.vitality-scoring-version"

STILL_TIME_SECONDS = 0.5
STILL_EMPTY_EDIT = 300  # 0x12c ticks at 600 Hz = 0.5 s
STILL_MEDIA_DURATION = 1

INFO_TIMESCALE = 60_000
INFO_SAMPLE_DELTA = 1_000
INFO_SAMPLE_COUNT = 60
INFO_SAMPLES_PER_CHUNK = 30
INFO_EMPTY_EDIT = 30  # ~0.05 s at 600 Hz
INFO_MEDIA_DURATION = INFO_SAMPLE_COUNT * INFO_SAMPLE_DELTA  # 60_000 = 1.0 s

# Neutral live-photo-info sample from the file iOS accepted. Repeated 60 times.
LIVE_PHOTO_INFO_SAMPLE = bytes.fromhex(
    "000000900000000103000000bdc36d3ce3b5eb6d800000007b80ad425a2d6441"
    "0a08cb3e7feea6bd79e9f63f000080400400ff00000000000000000000000000"
    "000000000000000007000000525e873ee66e52bf1b2a6ac4d37862bf761ed23d"
    "de3f8ec313f52f39b2f04439ff309dbf1a17f1ed1b070000206796ed1b070000"
    "00000000000000000000000000000000"
)
# still-image-time (0xFF) + identity transform (item 2).
STILL_IMAGE_SAMPLE = bytes.fromhex(
    "0000000900000001ff"
    "0000005000000002"
    "3ff0000000000000000000000000000000000000000000000000000000000000"
    "3ff0000000000000000000000000000000000000000000000000000000000000"
    "3ff0000000000000"
)

if len(LIVE_PHOTO_INFO_SAMPLE) != 144:
    raise RuntimeError(f"live-photo-info sample deve ter 144 bytes, tem {len(LIVE_PHOTO_INFO_SAMPLE)}")
if len(STILL_IMAGE_SAMPLE) != 89:
    raise RuntimeError(f"still-image-time sample deve ter 89 bytes, tem {len(STILL_IMAGE_SAMPLE)}")
