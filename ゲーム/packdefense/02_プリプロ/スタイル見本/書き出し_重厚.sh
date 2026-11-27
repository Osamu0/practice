#!/bin/sh
# 重厚の見本（案D・E・F、案Dの2頭身、大きな絵）を PNG に書き出す。game-preprod-art 2026-11-27
# 案Dの2頭身（第3版）は 作図_重厚_D_2頭身.py で SVG を作ってから書き出す。
# 剣士の作図で使っている shot.js（Playwright の Chromium）をそのまま使う。
# 実行：sh ゲーム/packdefense/02_プリプロ/スタイル見本/書き出し_重厚.sh
set -e
D="$(cd "$(dirname "$0")" && pwd)"
SHOT="$D/../../07_コンテンツ/デザイン/キャラ/剣士/作図/shot.js"
python3 "$D/作図_重厚_D_2頭身.py" > /dev/null
cd "$(dirname "$SHOT")"
for n in 重厚_D 重厚_E 重厚_F 重厚_D_2頭身; do
  node shot.js "$D/$n.svg" "$D/$n.png" 1
  node shot.js "$D/$n.svg" "$D/${n}_2倍.png" 2
done
node shot.js "$D/重厚_大きな絵.svg" "$D/重厚_大きな絵.png" 1
