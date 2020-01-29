#!/usr/bin/env python3

from os import path
import sys
import json

import argh
import sh

SCRIPT_DIR = path.abspath(path.dirname(__file__))

# Download LUT file from
# https://www.fujifilm.com/support/digital_cameras/software/lut/
LUT_FPATH = {
    'wdr': path.join(SCRIPT_DIR, 'lut/x-t30-wdr.cube'),
    'eterna': path.join(SCRIPT_DIR, 'lut/x-t30-eterna.cube'),
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
# - iPhone records 4K video uses bt709 for color space, trc and primaries.  It's
#   better for me to just follow Apple's settings.
def convert(input_fname, output_fname,
        duration=None,
        audio_enc='aac', vbr=0, bit_rate='256k',
        video_enc='libx265', color_space='bt709', lut=None):
    """
    lut: LUT to apply: wdr, eterna
    audio_enc: audio encoder: libfdk_aac, aac
    vbr: use Variable Bit Rate (VBR) mode to encode audio if not None, valid
        interge range: [1, 5]. Note only libfdk_aac uses this option
    bit_rate: audio encoding bit_rate, only used when vbr is set to 0
    video_enc: video encoder:  libx265, libx264
    color_space: specify color space, transfer, primaries with the specified
        value. If given 'none', keep color settings the same as input
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
        #venc_params += ':profile=main'
        ffmpeg = ffmpeg.bake('-x265-params', venc_params)
    elif video_enc == 'libx264':
        ffmpeg = ffmpeg.bake('-x264-params', venc_params)

    print(f'{ffmpeg} {output_fname}')
    ffmpeg(output_fname,
            _out=sys.stdout, _err=sys.stderr)


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


if __name__ == '__main__':
    argh.dispatch_commands(
            [convert, auto_convert, probe])

