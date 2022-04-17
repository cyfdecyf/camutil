#!/usr/bin/env python3

"""
Workflow for video files.
"""

import glob
import os
from os import path
import sys
from typing import List

import argh
import sh

import geotag


DEFAULT_OUTPUT_DIR = '000hevc'
DEFAULT_AVCONVERT_PRESET = 'PresetHEVC3840x2160'
OUTPUT_EXT = 'mov'


def convert_one_h265(fname: str, output_fname: str,
                     preset: str = DEFAULT_AVCONVERT_PRESET):
    sh.avconvert(
        verbose=True,
        preset=preset,
        source=fname, output=output_fname,
        _long_sep=' ',
        _out=sys.stdout, _err=sys.stderr)


@argh.arg('-f', '--fpath', action='extend', nargs='+', required=True)
def convert_h265(fpath: List[str] = None,
                 pattern: str = None,
                 output_dir: str = DEFAULT_OUTPUT_DIR,
                 preset: str = DEFAULT_AVCONVERT_PRESET) -> List[str]:
    """Converts video files to h.265 encoding, skip already converted files.

    Args:
        fpath: space separated files or directories to add geotag
        pattern: glob with this pattern for directories in fpath
        output_dir: generate output in this directory
        preset: preset for `avconvert`

    Returns:
        result: list of output file name
    """
    if not path.exists(output_dir):
        os.makedirs(output_dir)

    fpath = geotag.glob_extend(fpath, pattern)
    output_fpath = []
    for f in fpath:
        bname, ext = path.splitext(f)
        if ext == '':
            raise ValueError(f'{f} has no suffix, is it really a video file?')

        output_fname = path.join(output_dir, f'{bname}.{OUTPUT_EXT}')
        if path.exists(output_fname):
            print(f'skip convert {f}')
            continue

        print(f'convert {f} to {output_fname}')
        convert_one_h265(f, output_fname, preset=preset)
        output_fpath.append(output_fname)

    return output_fpath


def _bname(fname: str):
    return path.splitext(path.basename(fname))[0]


def _copy_time(fpath: List[str], output_fpath: List[str]):
    bname2src = {}
    for src in fpath:
        bn = _bname(src)
        existing_src = bname2src.get(bn)
        if existing_src:
            raise ValueError(f'duplicate file basename {existing_src} and {src}')
        bname2src[bn] = src

    for dst in output_fpath:
        bn = _bname(dst)
        src = bname2src.get(bn)
        if src is None:
            print(f'WARNING no src file found for {dst}')
            continue
        print(f'copy time from {src} to {dst}')
        geotag.copy_time(src, dst)


@argh.arg('-f', '--fpath', action='extend', nargs='+', required=True,
          help='space separated files or directories to add geotag')
@argh.arg('-g', '--gpslog', action='extend', nargs='+',
          help='space separated GPS log files')
@argh.arg('-a', '--action', action='extend', nargs='+', default=None,
          help='list of actions to run, order is ignored. Valid actions: convert, copy-time, geotag')
@argh.arg('-p', '--pattern',
          help='glob with this pattern for directories in fpath')
@argh.arg('-o', '--output-dir',
          help='output converted videos in this directory. For non-convert action, this is the directory to look for files to modify')
@argh.arg('-t', '--timezone',
          help='timezone for input video files, use hour offset to UTC to denote timezone, e.g. "+8" for Asia/Shanghai.'
               ' Refer to geotag.video for more details')
@argh.arg('--preset',
          help='preset for ``avconvert`` command')
def flow(fpath: List[str] = None,
         gpslog: List[str] = None,
         pattern: str = None,
         output_dir: str = '000hevc',
         action: List[str] = None,
         timezone: str = 'auto',
         preset: str = DEFAULT_AVCONVERT_PRESET):
    """Run work flow for video files."""
    if action is None:
        action = ['convert', 'copy-time', 'geotag']

    fpath = geotag.glob_extend(fpath, pattern)

    if 'convert' in action:
        output_fpath = convert_h265(fpath, pattern, output_dir, preset=preset)
    else:
        output_fpath = glob.glob(path.join(output_dir, f'*.{OUTPUT_EXT}'))
        output_fpath.sort()

    if len(output_fpath) == 0:
        print(f'no output files, exit')
        return

    if 'copy-time' in action:
        _copy_time(fpath, output_fpath)

    if 'geotag' in action:
        if gpslog is None:
            print('no gpslog, skip geotagg action')
            return

        geotag.video(output_fpath, gpslog=gpslog, timezone=timezone)


if __name__ == "__main__":
    argh.dispatch_commands([
        convert_h265,
        flow,
    ])
