#!/usr/bin/env python3

"""
Convert TIFF files to HEIC with `sips` command on macOS.

CaptureOne does not support export to HEIC files. So I choose to export as TIFF and then
use this script to convert TIFF to HEIC, along with adding geotags.

Also add geotag to converted HEIC files if gps log file is specified.
"""

from glob import glob
from typing import Optional
from os import path
import sys

import argh
import sh

import geotag


def _convert1(fname: str, quality: int):
    bname, ext = path.splitext(fname)
    if ext == '':
        raise ValueError(f'{fname} has no suffix, is it really an image file?')

    out_fname = f'{bname}.heic'

    sh.sips(
        '-s', 'format', 'heic',
        '-s', 'formatOptions', f'{quality}',
        '--out', out_fname,
        fname,
        _out=sys.stdout, _err=sys.stderr)
    return out_fname


@argh.arg('-f', '--fpath', action='extend', nargs='+', required=True)
@argh.arg('-g', '--gpslog', action='extend', nargs='+')
def convert_to_heic(fpath: str = None, gpslog: Optional[str] = None,
                    pattern='*.tif', quality: int = 89):
    """Convert image files to HEIC format.

    Args:
        fpath: space separated files or directories to add geotag
        gpslogs: GPS log files, comma separated list
        ext: when fpath is directory, glob with this file extension
        quality: quality for HEIC file, number range from 0-100
    """
    fpath = geotag.glob_extend(fpath, pattern)
    quality = int(quality)

    heic_flist = []
    for fname in fpath:
        heic_flist.append(_convert1(fname, quality))

    if len(heic_flist) > 0 and gpslog is not None:
        geotag.image(heic_flist, gpslog)


if __name__ == "__main__":
    argh.dispatch_command(convert_to_heic)
