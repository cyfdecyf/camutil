#!/bin/bash

set -e

if (( $# < 2 )); then
    echo "Usage: $(basename $0) <src> <dst> [dst2 [dst3 ...]]"
    exit 1
fi

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

src="$1"

copy_gps_tag() {
    local dst="$1"

    # -GPSPosition not writable.
    #exiftool -a -ee -tagsFromFile "$src" \
    #    -QuickTime:GPSCoordinates -GPSPosition $dst

    exiftool -a -ee -tagsFromFile "$src" \
        -GPSCoordinates -GPSAltitude -GPSAltitudeRef \
        -GPSLatitude -GPSLongitude "$dst"

    # If GPSCoordinates does not exists, add it.
    # This happens if src is an jpg file which does not have GPSCoordinates 
    if ! exiftool -GPSCoordinates "$dst" | grep -q Coordinates; then
        "$DIR/add-gps-coordinates.sh" "$dst"
    fi
}

shift 1
while (( $# > 0 )); do
    copy_gps_tag "$1"
    shift 1
done
