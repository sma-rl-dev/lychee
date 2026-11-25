#!/usr/bin/env bash
# Regenerates the committed seed fixtures in seed/photos with host ImageMagick.
# The committed JPEGs are the source of truth for `tester-env seed`; this script
# only documents how they were produced (same commands -> same visible images).
# Usage: ./seed/generate-fixtures.sh
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

# title|album dir|gradient from|gradient to|accent|shape
rows=(
  "Fjord at Blue Hour|Nordic Coast 2026|#12263a|#7fa6c3|#e8d5b7|circle 560,180 640,180"
  "Driftwood at Haukland Beach|Nordic Coast 2026|#5c6b73|#d9c7a7|#3f4a50|rectangle 120,380 680,470"
  "Sea Stack from the Ferry|Nordic Coast 2026|#2e4a5a|#9bb7c4|#1d2f39|polygon 400,120 560,470 240,470"
  "Rorbu Cabins in the Rain|Nordic Coast 2026|#6b3f2a|#a8b8c0|#f0e6d2|rectangle 200,300 380,500"
  "Trail Marker Above the Village|Nordic Coast 2026|#3d5a3c|#c8d6b9|#7a4f2a|rectangle 380,220 440,480"
  "Reine Harbour Reflections|Nordic Coast 2026/Lofoten Islands|#0f2b3d|#f2b880|#dce8ee|circle 400,300 520,300"
  "Sheep on the Coastal Road|Nordic Coast 2026/Lofoten Islands|#4c6b45|#e6e2d3|#2b2b2b|rectangle 100,400 700,520"
  "Northern Lights over Vestfjorden|Nordic Coast 2026/Lofoten Islands|#08131f|#1f7a5c|#8ff0c0|polygon 120,420 700,180 700,420"
  "Empty Pier at Dawn|Nordic Coast 2026/Lofoten Islands|#2b3d4f|#e9c6a0|#5b6b78|rectangle 300,380 500,520"
  "Ceramic Mug on Linen|Studio Sessions|#e7ddcf|#c9b8a4|#8c5a3c|circle 400,300 480,300"
  "Portrait with Window Light|Studio Sessions|#2a2622|#d8c6ae|#f2e6d6|rectangle 220,120 520,470"
  "Linen Swatches on Oak|Studio Sessions|#a9865f|#efe6d5|#6b4a2f|rectangle 120,180 680,420"
  "Backdrop Test Frame|Studio Sessions|#3a3a3a|#9a9a9a|#d0d0d0|rectangle 200,200 600,400"
  "Snow on the Fire Escape|Archive 2024|#45586b|#f1f5f8|#2b3540|rectangle 240,240 560,520"
  "Rooftop Water Tanks|Archive 2024|#6f7c8a|#cfd8df|#3c4650|circle 260,260 340,260"
  "Market Street in Motion|Archive 2024|#5b3a2e|#e0b07a|#f5ead5|rectangle 80,320 720,470"
  "Dock Crane at Sunset|Archive 2024|#3a2c3f|#e08f5a|#1d1a22|polygon 420,120 540,470 300,470"
)

for row in "${rows[@]}"; do
  IFS='|' read -r title album c1 c2 accent shape <<<"${row}"
  mkdir -p "photos/${album}"
  convert -size 800x600 "gradient:${c1}-${c2}" \
    -fill "${accent}" -stroke none -draw "${shape}" \
    -fill "rgba(255,255,255,0.18)" -draw "rectangle 40,40 760,64" \
    -quality 82 -strip "photos/${album}/${title}.jpg"
done

echo "generated $(find photos -name '*.jpg' | wc -l) fixtures"
