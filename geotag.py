#!/usr/bin/env python3

import glob
import os
from os import path
import shutil
import sys
from typing import Dict

import argh
import sh


SRC_DIR = path.abspath(path.dirname(__file__))
EXIF_DATE_TAGS = ['CreateDate', 'DateTimeOriginal', 'ModifyDate', 'DateCreated']
EXIF_VIDEO_DATE_TAGS = EXIF_DATE_TAGS + [
    "MediaCreateDate", "MediaModifyDate", "TrackCreateDate", "TrackModifyDate"]


def _exiftool_time_shift_option(time_shift, tags):
    """Generate exiftool time shift options.

    Args:
      time_shift: Shift how many hours. Can be negative integer value.
      tags: date time related tags
    """
    if time_shift[0] in ('+', '-'):
        sign = time_shift[0]
        time_shift = time_shift[1:]
    else:
        sign = '+'

    opt = [f'-{t}{sign}={time_shift}' for t in tags]
    return opt


def _exiftool_tag_option(tag_values : Dict[str, str]):
    return [f'-{k}={v}' for k, v in tag_values.items()]


def is_video(fname : str):
    fname = fname.lower()
    return fname.endswith("mov") or fname.endswith("mp4")


def read_exif_tag(fname, tags):
    """Read tags and return a dict containing tag & values."""
    cmd = sh.exiftool.bake("-s2", *[f"-{t}" for t in tags])
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
    is different than handling picture files.
    """
    video_opt = _exiftool_time_shift_option(shift, EXIF_VIDEO_DATE_TAGS)
    pic_opt = _exiftool_time_shift_option(shift, EXIF_VIDEO_DATE_TAGS)

    cmd_pic = sh.exiftool.bake(*video_opt, _out=sys.stdout, _err=sys.stderr)
    cmd_video = sh.exiftool.bake(*pic_opt, _out=sys.stdout, _err=sys.stderr)
    for f in fname:
        if is_video(f):
            cmd_video(f)
        else:
            cmd_pic(f)


def copy_gps(src, time_shift=None, *dst):
    """Copy GPS related tags from src to dst.

    Only tested on video destination file. (Because exiftool supports geotag picture file directly.)

    Args:
      time_shift: copy gps and shift time at the same time to avoid an extra
            file copy if doing these two actions separately
    """
    gps_tag_values = read_exif_tag(
        src,
        ["GPSCoordinates", "GPSAltitude", "GPSAltitudeRef",
         "GPSLatitude", "GPSLongitude", "GPSPosition", "GPSCoordinates"])

    if "GPSCoordinates" not in gps_tag_values:
        # iPhone's jpg file has no GPSCoordinates, so we only add that tag for video file.
        gps_tag_values["GPSCoordinates"] = \
            f'{gps_tag_values["GPSPosition"]}, {gps_tag_values["GPSAltitude"]}'

    cmd = sh.exiftool.bake(*_exiftool_tag_option(gps_tag_values))
    if time_shift:
        time_shift_option = _exiftool_time_shift_option(time_shift, EXIF_VIDEO_DATE_TAGS)
        cmd = cmd.bake(*time_shift_option)
    print(f"add GPS tag for video file {dst}")
    cmd(*dst, _out=sys.stdout, _err=sys.stderr)


def geotag(gpslog: str, fpath: str,
           video_pattern : str = "DSCF*.mov",
           tag_file_time_shift=None,
           time_shift=None):
    """Geotag for picture and video using [exiftool](https://exiftool.org/).

    exiftool can geotag all jpeg files under a single directory but not for mov (QuickTime) file.

    So for mov files, we copy an empty jpeg file and set it's creation time the same as the move file.
    Let exiftool do geo-tagging then copy the geotag to mov file.

    Args:
      gpslog: comma separated GPS log file
      fpath: either file or a directory, both jpg and video files will add geotag
      video_pattern: only used when fpath is a directory
      tag_file_time_shift: shift time (in hour) when generating temporary jpg tag file
      time_shift: shift time (in hour) when generating the geotagged file
    """
    if path.isdir(fpath):
        flist = glob.glob(path.join(fpath, video_pattern))
        flist.sort()
        dstdir = fpath
    else:
        flist = [fpath]
        dstdir = path.dirname(fpath)

    TAG_FILE = path.join(SRC_DIR, "tag.jpg")

    print('generate geotag tmp jpg files for each video file')
    video2tag = {} # For finding jpg tag file later.
    for vfile in flist:
        fname, _ = path.splitext(vfile)
        dst = f'{fname}_fuji_geotag_tmp.jpg'
        video2tag[vfile] = dst
        if path.exists(dst):
            os.unlink(dst)

        create_date = read_exif_tag(vfile, ['CreateDate'])['CreateDate']
        date_tag_values = {}
        for t in EXIF_DATE_TAGS:
            date_tag_values[t] = create_date

        cmd = sh.exiftool.bake(*_exiftool_tag_option(date_tag_values))
        # print("    copy create date from video file to jpg geotag file")
        cmd("-o", dst, TAG_FILE) #, _out=sys.stdout, _err=sys.stderr)

        if tag_file_time_shift:
            # print("    time shift for jpg geotag file")
            cmd = sh.exiftool.bake(
                "-overwrite_original",
                *_exiftool_time_shift_option(tag_file_time_shift, EXIF_DATE_TAGS))
            cmd(dst) #, _out=sys.stdout, _err=sys.stderr)
        print(f'\t{dst} created')

    # Geotag for all picture files.
    cmd = sh.exiftool.bake("-overwrite_original")
    for f in gpslog.split(","):
        cmd = cmd.bake("-geotag", f)
    print(f"====== geotag for all picture files in {dstdir} ======")
    cmd(*video2tag.values(), _out=sys.stdout, _err=sys.stderr)

    for vfile in flist:
        geotag_jpg_file = video2tag[vfile]
        copy_gps(geotag_jpg_file, time_shift, vfile)
        os.unlink(geotag_jpg_file)

if __name__ == "__main__":
    argh.dispatch_commands([
        shift_time,
        copy_gps,
        geotag,
    ])
