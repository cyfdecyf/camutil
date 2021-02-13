#!/bin/bash

set -e

SRCDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

if [[ $# != 1 ]]; then
    echo "Usage: $(basename $0) <dir>"
    exit 1
fi

export LD_LIBRARY_PATH=/share/CACHEDEV1_DATA/.qpkg/QPython3/lib

find "$1" -type f -name 'DSCF*.MOV' -exec fuji.py auto-convert {} \;

#$SRCDIR/fix-video-time.sh
