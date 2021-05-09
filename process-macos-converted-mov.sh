#!/bin/bash

set -e

# Run under subdirectory containing original (foo.MOV) and processed mov files (foo-1.mov).
# Process video files will move into "000hevc" directory.

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
GEOTAG_SCRIPT=$DIR/geotag.py

if [[ $# != 1 ]]; then
    echo "Usage: $(basename $0) <absolute path to geotag file>"
    exit 1
fi
geotag_file=$1

WORKDIR=000hevc
mkdir -p $WORKDIR

for i in DSCF*-1.mov; do
    dst=$WORKDIR/${i%-1.mov}.mov
    echo mv $i $dst
    mv $i $dst

    # Fix macOS encode service changing time information.
    echo copy-time ${i%-1.mov}.MOV $dst
    $GEOTAG_SCRIPT copy-time ${i%-1.mov}.MOV $dst
done

echo "add geotag"
# When importing video file into Photos, the time format is considered as UTC by Photos.
#Thus we shift time to UTC here.
$GEOTAG_SCRIPT geotag --time-shift -8 $geotag_file $WORKDIR
