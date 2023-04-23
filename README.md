Collection of scripts to process camera image and video files (on macOS).

Tested with Python 3.9. (Requires Python >= 3.8.)

Some scripts are for specific camera vendors:

- Fujifilm
  - Transcoding with fujifilm's LUT file

Relies on macOS features:

- Encode service to convert video files to HEVC format
  - Personally I can't see difference between 100Mbps H.264 and
    the converted video. So I use this to save (a lot of) storage space
- `sips` command to do image file conversion

# Geotagging

I use a GPS logger [Columbus P1](https://www.cbgps.com/p1/index_en.htm) to record in NMEA format.
Geotagging is done by [exiftool](https://exiftool.org/).

## Geotagging images

For image files, this is rather simple, use `exiftool` directly:

```
exiftool -geotag log1.txt [-geotag log2.txt] <images or dir>
```

This can process multiple image files in a single command.

## Geotagging videos

The [geotag.py](./geotag.py) script helps to geotag videos. Because exiftool can't geotag video files directly,
the script uses the following method:

1. Copy video time to jpg files
2. Geotag all jpg files
3. Copy GPS information from jpg files back to corresponding video file

My current workflow for processing video files works like this:

1. Convert from H.264 to H.265 (HEVC) on macOS using encode service inside Finder.app
    - macOS's convert service does not copy video creation time. It also ignores `Make` and `Model` tag.
2. Run [process-macos-converted-mov.sh](./process-macos-converted-mov.sh) under directory containing video files.
   - Checkout that script for details

# Transcoding

[fuji.py](./ffmpeg.py) provides command to convert H.264 encoded video to H.265 format using [ffmpeg](https://ffmpeg.org/).
If you put video file in directory named `F-log`, then the script will apply lut when converting.

For ordinary users, I think there's few reason to use F-log. Film simulation with high dynamic range usually gives
me more pleasant color and conversion using macOS's encode service is much faster.
