#!/bin/sh
# 重厚の見本（案D・E・F、大きな絵）を PNG に書き出す。game-preprod-art 2026-11-27
# 剣士の作図で使っている shot.js（Playwright の Chromium）をそのまま使う。
# 実行：sh ゲーム/packdefense/02_プリプロ/スタイル見本/書き出し_重厚.sh
set -e
D="$(cd "$(dirname "$0")" && pwd)"
SHOT="$D/../../07_コンテンツ/デザイン/キャラ/剣士/作図/shot.js"
cd "$(dirname "$SHOT")"
for n in 重厚_D 重厚_E 重厚_F; do
  node shot.js "$D/$n.svg" "$D/$n.png" 1
  node shot.js "$D/$n.svg" "$D/${n}_2倍.png" 2
done
node shot.js "$D/重厚_大きな絵.svg" "$D/重厚_大きな絵.png" 1
