#!/usr/bin/env python3

import datetime
import glob
import os
from os import path
import re
import sys
from typing import Dict, List, Optional, Union

import argh
import sh


SRC_DIR = path.abspath(path.dirname(__file__))
EXIF_DATE_TAGS = ['CreateDate', 'DateTimeOriginal', 'ModifyDate', 'DateCreated']
#EXIF_DATE_TAGS = ['CreateDate', 'DateTimeOriginal', 'ModifyDate', 'DateCreated', 'IPTC:TimeCreated', 'IPTC:DigitalCreationTime']
EXIF_VIDEO_DATE_TAGS = EXIF_DATE_TAGS + [
    "MediaCreateDate", "MediaModifyDate", "TrackCreateDate", "TrackModifyDate"]
GPS_TAGS = ["GPSCoordinates", "GPSAltitude", "GPSAltitudeRef",
         "GPSLatitude", "GPSLongitude", "GPSPosition", "GPSCoordinates"]

# Sony uses DeviceManufacturer and DeviceModelName instead of Make and Model.
# But exiftool doesn't support writing these tags.
# So we map these tags to Make and Model.
EXIF_CAMERA_MODEL_TAGS = {
    'Make': None,
    'Model': None,
    'DeviceManufacturer': 'Make',
    'DeviceModelName': 'Model',
}


DEFAULT_CAMERA_MODEL = {
    'SONY': 'ICLE-7M4',
}


# It's possible that I rename file to add information about the video.
_FNAME_RE_SONY = re.compile(r'C\d\d\d\d.*\.MP4')


def guess_camera_maker(fname: str):
    if 'DSCF' in fname:
        return 'Fujifilm'

    if _FNAME_RE_SONY.match(fname):
        print('matched sony file')
        return 'SONY'

    return None


def _canonic_camera_model_tag(fname: str, tag_values: Dict[str, str]):
    for tag, canonic_tag in EXIF_CAMERA_MODEL_TAGS.items():
        if canonic_tag is None or tag not in tag_values:
            continue

        tag_values[canonic_tag] = tag_values[tag]
        del tag_values[tag]

    if 'Make' not in tag_values:
        maker = guess_camera_maker(fname)
        if maker:
            tag_values['Make'] = maker

    if 'Model' not in tag_values:
        model = DEFAULT_CAMERA_MODEL.get(tag_values['Make'], None)
        if model:
            tag_values['Model'] = model



LOCAL_TZ_SHIFT_HOUR = int(datetime.datetime.utcnow().astimezone().utcoffset().total_seconds() / 3600)


def _guess_video_file_time_zone(fname: str):
    maker = guess_camera_maker(fname)
    # Fujifilm camera's video uses local time zone.
    if maker == 'Fujifilm':
        return LOCAL_TZ_SHIFT_HOUR
    else:
        return 0


def _shift_to_utc_timezone(timezone: int):
    return -timezone


def _shift_to_local_timezone(timezone: int):
    utcshift = _shift_to_utc_timezone(timezone)
    return utcshift + LOCAL_TZ_SHIFT_HOUR


def _exiftool_time_shift_option(time_shift: int, tags: List[str]):
    """Generate exiftool time shift options.

    Args:
      time_shift: shift how many hours. Can be negative integer value.
      tags: date time related tags
    """
    if time_shift < 0:
        sign = '-'
        time_shift = -time_shift
    else:
        sign = '+'

    opt = [f'-{t}{sign}={time_shift}' for t in tags]
    return opt


def _exiftool_tag_option(tag_values : Dict[str, str], exclude_keys=[]):
    return [f'-{k}={v}' for k, v in tag_values.items() if k not in exclude_keys]


def _filter_no_gps_tag_file(fpath: List[str]):
    """Keep only files that have no GPS tags."""
    notag_fpath = [f for f in fpath if len(read_exif_tag(f, GPS_TAGS)) == 0]
    if len(notag_fpath) != len(fpath):
        skip = set(fpath) - set(notag_fpath)
        print(f'skip tagging already geotagged files: {", ".join(skip)}')
    return notag_fpath


def glob_extend(fpath: List[str], pattern: str):
    if pattern is None:
        return fpath

    lst = []
    for f in fpath:
        if path.isdir(f):
            matches = glob.glob(path.join(f, pattern))
            matches.sort()
            lst.extend(matches)
        else:
            lst.append(f)
    return lst


def is_video(fname: str):
    fname = fname.lower()
    return fname.endswith("mov") or fname.endswith("mp4")


exiftool = sh.exiftool.bake("-api", "largefilesupport=1")


def read_exif_tag(fname: str, tags: List[str]) -> Dict[str, str]:
    """Read tags and return a dict containing tag & values."""
    cmd = exiftool.bake("-api", "largefilesupport=1", "-s2", *[f"-{t}" for t in tags])
    out = cmd(fname)

    r = {}
    for l in out.stdout.decode('utf-8').splitlines():
        k, v = l.split(': ', 1)
        r[k] = v
    return r


def shift_time(shift, *fname):
    """Shift time.

    Most useful to convert video file time to UTC. Apple's Photos app
    considers vidoe date time without time zone info as in UTC. This behavior
    is different from handling picture files.
    """
    video_opt = _exiftool_time_shift_option(shift, EXIF_VIDEO_DATE_TAGS)
    pic_opt = _exiftool_time_shift_option(shift, EXIF_DATE_TAGS)

    cmd_pic = exiftool.bake(*pic_opt, _out=sys.stdout, _err=sys.stderr)
    cmd_video = exiftool.bake(*video_opt, _out=sys.stdout, _err=sys.stderr)
    for f in fname:
        if is_video(f):
            cmd_video(f)
        else:
            cmd_pic(f)


def copy_time(src, *dst):
    """Copy create, modify date time and extra tags from src to dst.

    macOS convert video service changes video create, modify date time and drops
    some other tags. Use this to copy these tags from original video file.
    """
    TIME_TAGS = [
            "TrackCreateDate", "TrackModifyDate", "MediaCreateDate",
            "MediaModifyDate", "ModifyDate", "DateTimeOriginal", "CreateDate"]

    tag_values = read_exif_tag(src, TIME_TAGS + list(EXIF_CAMERA_MODEL_TAGS.keys()))
    _canonic_camera_model_tag(src, tag_values)

    exiftool(_exiftool_tag_option(tag_values), dst,
                _out=sys.stdout, _err=sys.stderr)


def copy_gps(src, *dst, time_shift: Optional[Union[int, str]] = 0):
    """Copy GPS related tags from src to dst.

    Args:
        time_shift: copy gps and shift time at the same time to avoid an extra
            file copy if doing these two actions separately. Specify 'auto' to guess time_shift
            based on first destination file name.
    """
    if time_shift == 'auto':
        time_zone = _guess_video_file_time_zone(dst[0])
        time_shift = _shift_to_utc_timezone(time_zone)
    elif isinstance(time_shift, str):
        time_shift = int(time_shift)

    gps_tag_values = read_exif_tag(src, GPS_TAGS)

    if "GPSCoordinates" not in gps_tag_values and \
            ("GPSPosition" in gps_tag_values and "GPSAltitude" in gps_tag_values):
        # iPhone's jpg file has no GPSCoordinates, so we only add that tag for video file.
        gps_tag_values["GPSCoordinates"] = \
            f'{gps_tag_values["GPSPosition"]}, {gps_tag_values["GPSAltitude"]}'

    # GPSPosition is a composite tag (combined from other tags) thus not
    # writable.
    cmd = exiftool.bake(*_exiftool_tag_option(gps_tag_values, exclude_keys=["GPSPosition"]))
    if time_shift != 0:
        time_shift_option = _exiftool_time_shift_option(time_shift, EXIF_VIDEO_DATE_TAGS)
        cmd = cmd.bake(*time_shift_option)
    print(f"add GPS tag for video file {dst}")
    cmd(*dst, _out=sys.stdout, _err=sys.stderr)


@argh.arg('-f', '--fpath', action='extend', nargs='+', required=True,
          help='space separated files or directories to add geotag')
@argh.arg('-g', '--gpslog', action='extend', nargs='+', required=True,
          help='space separated GPS log files')
@argh.arg('-p', '--pattern',
          help='glob with this pattern for directories in fpath')
@argh.arg('-o', '--overwrite-original',
          help=' whether create copy of original file')
@argh.arg('--force',
          help='update GPS tag even if image files already contain GPS tags.')
def image(fpath: List[str] = None,
          gpslog: List[str] = None,
          pattern: str = '*.jpg',
          overwrite_original: bool = False,
          force: bool = False):
    """Add geotag for image files."""
    fpath = glob_extend(fpath, pattern)

    if not force:
        fpath = _filter_no_gps_tag_file(fpath)

    cmd = exiftool
    if overwrite_original:
        cmd = cmd.bake("-overwrite_original")

    for f in gpslog:
        cmd = cmd.bake("-geotag", f)

    cmd(*fpath, _out=sys.stdout, _err=sys.stderr)


@argh.arg('-f', '--fpath', action='extend', nargs='+', required=True,
          help='space separated files or directories to add geotag')
@argh.arg('-g', '--gpslog', action='extend', nargs='+', required=True,
          help='space separated GPS log files')
@argh.arg('-p', '--pattern',
          help='glob with this pattern for directories in fpath')
@argh.arg('-t', '--timezone',
          help='timezone for input video files, use hour offset to UTC to denote timezone, e.g. "+8" for Asia/Shanghai. '
               'Defaults to auto which makes guess based on file name')
@argh.arg('--force',
          help='update GPS tag even if image files already contain GPS tags.')
def video(fpath: List[str] = None,
          gpslog: List[str] = None,
          pattern: str = None,
          timezone: str = 'auto',
          force: bool = False):
    """Geotag for video files using [exiftool](https://exiftool.org/).

    exiftool can geotag all jpeg files under a single directory but not for mov (QuickTime) file.

    So for mov files, we copy an empty jpeg file and set its creation time the same as the move file.
    Let exiftool do geotag then copy the geotag to mov file.

    For timezones:

    - The final video files' creation time is in UTC
      - macOS Photos will shift video time to local timezone
    - Temporary image files used for geotagging is in local timezone
    """
    fpath = glob_extend(fpath, pattern)

    if not force:
        fpath = _filter_no_gps_tag_file(fpath)

    if timezone == 'auto':
        timezone = _guess_video_file_time_zone(fpath[0])
    else:
        timezone = int(timezone)

    time_shift = _shift_to_utc_timezone(timezone)
    tag_file_time_shift = _shift_to_local_timezone(timezone)

    TAG_FILE = path.join(SRC_DIR, "tag.jpg")

    print('====== generate geotag tmp jpg files for each video file ======')
    video2tag = {}  # For finding jpg tag file later.
    for vfile in fpath:
        fname, _ = path.splitext(vfile)
        dst = f'{fname}_fuji_geotag_tmp.jpg'
        video2tag[vfile] = dst
        if path.exists(dst):
            os.unlink(dst)

        create_date = read_exif_tag(vfile, ['CreateDate'])['CreateDate']
        date_tag_values = {}
        for t in EXIF_DATE_TAGS:
            date_tag_values[t] = create_date

        cmd = exiftool.bake(*_exiftool_tag_option(date_tag_values))
        # print("    copy create date from video file to jpg geotag file")
        cmd("-o", dst, TAG_FILE, _err=sys.stderr) #, _out=sys.stdout

        if tag_file_time_shift != 0:
            # print(f"    time shift {tag_file_time_shift} for tmp jpg geotag file")
            cmd = exiftool.bake(
                "-overwrite_original",
                *_exiftool_time_shift_option(tag_file_time_shift, EXIF_DATE_TAGS))
            cmd(dst, _out=sys.stdout, _err=sys.stderr)
        print(f'\t{dst} created')

    print('====== geotag for all tmp jpg files ======')
    image(video2tag.values(), gpslog, overwrite_original=True)

    print('====== copy GPS from tmp jpg to video ======')
    for vfile in fpath:
        geotag_jpg_file = video2tag[vfile]
        copy_gps(geotag_jpg_file, vfile, time_shift=time_shift)
        os.unlink(geotag_jpg_file)


if __name__ == "__main__":
    argh.dispatch_commands([
        shift_time,
        copy_time,
        copy_gps,
        video,
        image,
    ])
