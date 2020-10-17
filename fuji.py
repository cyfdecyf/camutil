#!/usr/bin/env python3

import glob
import json
import multiprocessing
import os
from os import path
import shutil
import sys
from typing import Dict

import argh
import sh

SRC_DIR = path.abspath(path.dirname(__file__))

# Download LUT file from
# https://www.fujifilm.com/support/digital_cameras/software/lut/
LUT_FPATH = {
    'wdr': path.join(SRC_DIR, 'lut/x-t30-wdr.cube'),
    'eterna': path.join(SRC_DIR, 'lut/x-t30-eterna.cube'),
}

VIDEO_OPTIONS = {
    # FFmpeg docs says CRF "subjectively sane range is 17-28", thus we use 17.
    # https://trac.ffmpeg.org/wiki/Encode/H.264#a1.ChooseaCRFvalue
    'libx264': {
        'crf': 17,
        'preset': 'slow',
    },
    # According to following article, use crf 20 and slow preset.
    # The author can't see differences between crf 22 and 20 by eye, but
    # objective measurement shows there's still differences.
    # https://codecalamity.com/encoding-settings-for-hdr-4k-videos-using-10-bit-x265
    #
    # Encoding with slow preset is too slow on qnap with J3455 CPU, thus I
    # change preset to medium. Setting crf 20 produces 90Mbps bit rate for some
    # video which results files too large, thus I set it to 22 to save more file
    # spaces.
    'libx265': {
        'crf': 22,
        'preset': 'medium'
    },
}

FRAMERATE_MAPPING = {
    '24/1': 24,
    '24000/1001': 24,
    '25/1': 25,
    '30/1': 30,
    '30000/1001': 30,
    '60000/1001': 60,
}


def probe(input_fname):
    """Use ffprobe to get video file metadata."""
    try:
        probe = sh.ffprobe(
            '-print_format', 'json',
            '-show_format', '-show_streams',
            input_fname)
    except sh.ErrorReturnCode_1 as e:
        print('error running ffprobe:\n'
              f'RUN:\n{e.full_cmd}\n\n'
              f'STDOUT:\n{e.stdout}\n\n'
              f'STDERR:\n{e.stderr}')
        sys.exit(1)

    probe_meta = json.loads(probe.stdout)
    metadata = {}

    # Copy video metadata.
    video_meta = probe_meta['streams'][0]
    if video_meta['codec_type'] != 'video':
        print('stream 0 is not video')
        sys.exit(1)

    vmeta = {}
    common_meta = ['codec_name', 'bit_rate', 'duration']
    # Not sure how to specify chroma location in encoding.
    # But X-T3 HEVC output video have chroma_location unspecified, maybe this
    # is not important.
    for k in common_meta + ['avg_frame_rate', 'pix_fmt',
                            'color_range', 'color_space', 'color_transfer', 'color_primaries',
                            'chroma_location']:
        vmeta[k] = video_meta.get(k, None)
    metadata['video'] = vmeta

    audio_meta = probe_meta['streams'][1]
    if audio_meta['codec_type'] != 'audio':
        print('stream 1 is not audio')
        sys.exit(1)

    ameta = {}
    for k in common_meta + ['sample_rate']:
        ameta[k] = audio_meta[k]
    metadata['audio'] = ameta

    return metadata


# About defaulting to bt709 color space:
# - Fujifilm provided LUT complies to ITU-R BT.709, thus I guess we
#   should force use the bt709 color space.
# - Fujifilm X-T30 records MOV file with PAL color space, which has some visible
#   color defects I've noticed, converting to bt709 makes the color seems more
#   correct on an sRGB display.
# - iPhone records 4K video uses bt709 for color space, trc and primaries.  It's
#   better for me to just follow Apple's settings.
def convert(input_fname, output_fname,
            duration=None,
            audio_enc='aac', vbr=0, bit_rate='256k',
            video_enc='libx265', color_space='bt709', lut=None,
            threads=None):
    """
    lut: LUT to apply: wdr, eterna
    audio_enc: audio encoder: libfdk_aac, aac
    vbr: use Variable Bit Rate (VBR) mode to encode audio if not None, valid
        interge range: [1, 5]. Note only libfdk_aac uses this option
    bit_rate: audio encoding bit_rate, only used when vbr is set to 0
    video_enc: video encoder:  libx265, libx264
    color_space: specify color space, transfer, primaries with the specified
        value. If given 'none', keep color settings the same as input
    threads: number of threads to use, default is min(4, #cpu_cores)
    """
    if input_fname == output_fname:
        print('error: input and output file name are the same.')
        sys.exit(1)

    if audio_enc not in ('aac', 'libfdk_aac'):
        print(f'invalid audio encoder: {audio_enc}')
        sys.exit(1)
    if video_enc not in ('libx264', 'libx265'):
        print(f'invalid video encoder: {video_enc}')
        sys.exit(1)

    if threads is None:
        threads = min(4, multiprocessing.cpu_count())

    metadata = probe(input_fname)

    ffmpeg = sh.ffmpeg.bake('-y')
    # Input options.
    if duration:
        ffmpeg = ffmpeg.bake('-t', duration)
    ffmpeg = ffmpeg.bake('-i', input_fname)

    # Followings are output options.

    # Audio options.
    if 'pcm' not in metadata['audio']['codec_name']:
        # For anything that's not pcm, just copy audio stream without encoding.
        ffmpeg = ffmpeg.bake('-c:a', 'copy')
    else:
        ffmpeg = ffmpeg.bake('-c:a', audio_enc)
        if vbr != 0:
            ffmpeg = ffmpeg.bake('-vbr', vbr)
        else:
            ffmpeg = ffmpeg.bake('-b:a', bit_rate)

    # Video options.
    video_options = VIDEO_OPTIONS[video_enc]

    video_meta = metadata['video']

    ffmpeg = ffmpeg.bake(
        '-c:v', video_enc,
        '-crf', video_options['crf'],
        '-preset', video_options['preset'],
        # Copy metadata so we can reserve video creation time etc.
        '-map_metadata', 0,
        # Write custom tags. According to https://superuser.com/a/1208277/87009
        '-movflags', 'use_metadata_tags',
        # Color related options.
        '-pix_fmt', video_meta['pix_fmt'],
        # For writing color atom. (Show things like HD (1-1-1) in QuickTime Player inspector.)
        '-movflags', '+write_colr', '-strict', 'experimental')
    if video_meta['color_range'] is not None:
        ffmpeg = ffmpeg.bake('-color_range', video_meta['color_range'])

    if color_space == 'none':
        # Keep color settings the same as input.
        ffmpeg = ffmpeg.bake(
            '-colorspace', video_meta['color_space'],
            '-color_trc', video_meta['color_transfer'],
            '-color_primaries', video_meta['color_primaries'])
    else:
        ffmpeg = ffmpeg.bake(
            '-colorspace', color_space,
            '-color_trc', color_space,
            '-color_primaries', color_space)

    if video_enc == 'libx265':
        # For QuickTime Player to know it's able to play this file.
        ffmpeg = ffmpeg.bake('-tag:v', 'hvc1')
    if lut:
        ffmpeg = ffmpeg.bake(
            '-vf', 'lut3d={}'.format(LUT_FPATH[lut]))

    frame_rate = FRAMERATE_MAPPING[metadata['video']['avg_frame_rate']]
    # Set keyint is 2x framerate, min-keyint to framerate, as recommended
    # https://en.wikibooks.org/wiki/MeGUI/x264_Settings#keyint
    # This limits gap between keyframes to be less than two seconds.
    # Refer to GOP on wikipedia to get more information.
    # Specifying colorprim, bt709 etc. combined with movflags write_colr will
    # store color space info in metadata.
    venc_params = f'keyint={frame_rate * 2}:min-keyint={frame_rate}'
    #venc_params = f'keyint={frame_rate * 2}:min-keyint={frame_rate}:colorprim=bt709:transfer=bt709:colormatrix=bt709'
    if video_enc == 'libx265':
        # Let ffmpeg to specify profile.
        # venc_params += ':profile=main'
        ffmpeg = ffmpeg.bake('-x265-params', venc_params + f':pools={threads}')
    elif video_enc == 'libx264':
        ffmpeg = ffmpeg.bake('-x264-params', venc_params)

    print(f'{ffmpeg} {output_fname}')
    ffmpeg('-threads', threads, output_fname, _out=sys.stdout, _err=sys.stderr)


def auto_convert(input_fname):
    """
    Automatically guess options and what to do with input file.
    """
    if 'original' in input_fname:
        print(f'skip converting {input_fname}')
        return

    outdir = path.dirname(input_fname)
    if outdir == '':
        outdir = '.'
    converting_dir = path.join(outdir, 'converting')
    sh.mkdir('-p', converting_dir)
    out_basename = path.splitext(path.basename(input_fname))[0] + '.mov'
    out_fname = path.join(converting_dir, out_basename)

    if 'F-Log' in input_fname:
        print(f'convert {input_fname} with lut')
        lut = 'wdr'
    else:
        print(f'convert {input_fname} without lut')
        lut = None
    convert(input_fname, out_fname, lut=lut)

    original_dir = path.join(path.dirname(input_fname), 'original')
    sh.mkdir('-p', original_dir)
    sh.mv(input_fname, original_dir)

    sh.mv('-f', out_fname, outdir)


def exiftool_read_tag(fname, *tags):
    """Read tags and return a dict containing tag & values."""
    cmd = sh.exiftool.bake("-s2", *[f"-{t}" for t in tags])
    out = cmd(fname)

    r = {}
    for l in out.stdout.decode('utf-8').splitlines():
        k, v = l.split(':', 1)
        r[k] = v
    return r


def _exiftool_time_shift_option(time_shift, *tags):
    if time_shift[0] == '-':
        sign = '-'
        time_shift = time_shift[1:]
    else:
        sign = '+'

    opt = [f'-{t}{sign}={time_shift}' for t in tags]
    return opt


def _exiftool_tag_option(tag_values : Dict[str, str]):
    return [f'-{k}={v}' for k, v in tag_values.items()]


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

        date_tags = ['CreateDate', 'DateTimeOriginal', 'ModifyDate', 'DateCreated']
        create_date = exiftool_read_tag(vfile, 'CreateDate')
        date_tag_values = {}
        for t in date_tags:
            date_tag_values[t] = create_date

        cmd = sh.exiftool.bake(*_exiftool_tag_option(date_tag_values))
        # print("    copy create date from video file to jpg geotag file")
        cmd("-o", dst, TAG_FILE) #, _out=sys.stdout, _err=sys.stderr)

        if tag_file_time_shift:
            # print("    time shift for jpg geotag file")
            cmd = sh.exiftool.bake(
                "-overwrite_original",
                *_exiftool_time_shift_option(tag_file_time_shift, *date_tags))
            cmd(dst) #, _out=sys.stdout, _err=sys.stderr)
        print(f'\t{dst} created')

    # Geotag for all picture files.
    cmd = sh.exiftool.bake("-overwrite_original")
    for f in gpslog.split(","):
        cmd = cmd.bake("-geotag", f)
    print(f"====== geotag for all jpg files in {dstdir} ======")
    cmd(*video2tag.values(), _out=sys.stdout, _err=sys.stderr)

    time_shift_option = {}
    if time_shift:
        time_shift_option = _exiftool_time_shift_option(
            time_shift,
            "DateTimeOriginal", "CreateDate", "ModifyDate",
            "MediaCreateDate", "MediaModifyDate",
            "TrackCreateDate", "TrackModifyDate")

    for vfile in flist:
        geotag_jpg_file = video2tag[vfile]
        gps_tag_values = exiftool_read_tag(geotag_jpg_file,
            "GPSCoordinates", "GPSAltitude", "GPSAltitudeRef",
            "GPSLatitude", "GPSLongitude", "GPSPosition")
        gps_tag_values["GPSCoordinates"] = f'{gps_tag_values["GPSPosition"]}, {gps_tag_values["GPSAltitude"]}'
        cmd = sh.exiftool.bake(*_exiftool_tag_option(gps_tag_values))
        if time_shift:
            cmd = cmd.bake(*time_shift_option)
        print(f"geotag for video file {vfile}")
        cmd(vfile, _out=sys.stdout, _err=sys.stderr)

        os.unlink(geotag_jpg_file)


if __name__ == "__main__":
    argh.dispatch_commands(
        [convert,
         auto_convert,
         probe,
         geotag])
