#!/bin/bash

# -overwrite_original
# The following three tag would generate warning about invalid time format.
# So we use -AllDates shortcut tag.
# -DateTimeOriginal-=8 -CreateDate=-8 -ModifyDate-=8 \

find . -name 'DSCF*.mov' -print -exec \
    exiftool \
    -AllDates-=8 -CreateDate-=8 -ModifyDate-=8 -MediaCreateDate-=8 -MediaModifyDate-=8 -TrackCreateDate-=8 -TrackModifyDate-=8 \
    -Make=FUJIFILM -Model=X-T30 \
    {} \;
