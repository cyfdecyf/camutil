#!/bin/bash

if [[ $# != 1 ]]; then
    echo "Usage: $(basename $0) <dir or file>"
    exit 1
fi

geotags_opt=""

for t in *.TXT; do
    geotag_opt="$geotag_opt -geotag=$t"
done

#exiftool $geotag_opt $1
exiftool $geotag_opt -QuickTime:GPSCoordinates $1
