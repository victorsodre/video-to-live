# video-to-live

Create an iPhone Lock Screen Live Photo from a short video. The local browser interface is English-first and includes a Brazilian Portuguese option; conversion always runs on your machine.

This project reproduces a package that was accepted by a test iPhone on 2026-08-26. iOS ultimately decides whether a transferred asset animates, so treat this as a reproducible local recipe, not a platform guarantee.

## Requirements

Use Python 3.10+ and an ffmpeg build with libx265.

~~~bash
brew install ffmpeg                # macOS
# sudo apt-get install ffmpeg      # Debian/Ubuntu

git clone https://github.com/victorsodre/video-to-live
cd video-to-live
ffmpeg -hide_banner -encoders | grep libx265
~~~

## Local interface

~~~bash
python3 -m video_to_live serve
~~~

Open http://127.0.0.1:8765/, choose a video, set the start and end handles, and select **Create Live Photo**. The Lock Screen uses about one second; longer clips are sped up to fit. Select **Português (Brasil)** in the interface when preferred.

The page accepts uploads up to 128 MiB and runs one conversion at a time. It accepts only local, same-origin requests, permits at most four simultaneous connections, and gives incomplete uploads 15 seconds of idle time. Media processes stop after 120 seconds and ffprobe calls after 30 seconds. Use the CLI for files above the upload limit.

## Transfer to iPhone

1. Unzip the download if needed.
2. AirDrop the .pvt **folder**.
3. Receive it in **Photos**, not Files.
4. Choose the Live Photo from the Lock Screen photo picker.

## Command line

~~~bash
python3 -m video_to_live clip.mp4
python3 -m video_to_live clip.mp4 --start 2.4 --end 8.1 -o output/
~~~

--start and --end are seconds; without them, the first second is used. The command creates clip.pvt/ and the adjacent HEIC+MOV pair. AirDrop the .pvt folder to Photos rather than sending a standalone zip or loose JPG+MOV pair.

The still is a 1080×1920 JPEG/JFIF named .HEIC, with MakerApple[17] set to the MOV UUID.

## Known compatibility constraints

- **H.264 / avc1:** the tested Lock Screen ignored it.
- **Original-speed long clips:** a native three-second clip was not accepted; this recipe uses a 1.05-second container and speeds a longer selected range up.
- **Other dimensions:** 1320×2868 (iPhone 16 Pro Max) was not accepted in this test; the recipe uses 1080×1920.
- **ffmpeg -c copy for mebx tracks:** it changes the timing tag to stts, which iOS ignored. This project writes the required atoms directly.

## Recipe

The video is HEVC encoded with:

~~~text
-c:v libx265
-tag:v hvc1
-pix_fmt yuv420p
-r 60
-t 1
-frames:v 60
scale/pad 1080x1920
-movie_timescale 600
-video_track_timescale 600
-brand qt
-movflags +faststart
-an
~~~

The muxer writes a 1.05-second container (mvhd 630/600), stts 59×10 + 1×30, Core Media Video, only content.identifier and live-photo.auto=1, plus two mebx tracks: live-photo-info (60 samples) and still-image-time (one sample at 0.5 seconds). It does not set a vitality score.

No third-party media is included. Generate the procedural demo locally:

~~~bash
python3 -m video_to_live --make-demo demo/orbits.mp4
python3 -m video_to_live demo/orbits.mp4 -o /tmp/live
~~~

## License

[MIT](LICENSE). Victor ([@ovictor](https://github.com/ovictor)).
