#!/bin/bash

if [[ $# != 2 ]]; then
    echo "Usage: $(basename $0) <src> <dst>"
    exit 1
fi

src=$1
dst=$2

# -GPSPosition not writable.
#exiftool -a -ee -tagsFromFile "$src" \
#    -QuickTime:GPSCoordinates -GPSPosition $dst

exiftool -a -ee -tagsFromFile "$src" \
    -GPSCoordinates -GPSAltitude -GPSAltitudeRef \
    -GPSLatitude -GPSLongitude "$dst"

# If GPSCoordinates does not exists, add it.
# This happens if src is an jpg file which does not have GPSCoordinates 
if ! exiftool -GPSCoordinates "$dst" | grep -q Coordinates; then 
    add-gps-coordinates.sh "$dst"
fi
