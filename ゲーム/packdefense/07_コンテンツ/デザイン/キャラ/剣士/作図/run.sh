#!/bin/sh
# すべて作り直す。作図/ で実行： sh run.sh
set -e
cd "$(dirname "$0")"
node lineup_sheet.js ../並べ図.svg && node shot.js ../並べ図.svg ../並べ図.png 1
node sheet.js ../設定画.svg && node shot.js ../設定画.svg ../設定画.png 1
node screen.js
G=../画面確認
node shot.js $G/戦場_差し替え.svg $G/戦場_差し替え_1倍.png 1
node shot.js $G/戦場_差し替え.svg $G/戦場_差し替え_3倍.png 3
node shot.js $G/戦場_差し替え_白黒.svg $G/戦場_差し替え_白黒_3倍.png 3
node shot.js $G/戦場_差し替え_半分.svg $G/戦場_差し替え_半分_3倍.png 3
node shot.js $G/混雑.svg $G/混雑_3倍.png 3
node shot.js $G/混雑.svg $G/混雑_1倍.png 1
node shot.js $G/混雑_白黒.svg $G/混雑_白黒_3倍.png 3
python3 -c "
from PIL import Image
G='../画面確認/'
a=Image.open(G+'戦場_差し替え_3倍.png').crop((330,1050,1170,1650)); a.save(G+'拡大_塔のまわり_3倍.png')
b=Image.open(G+'戦場_差し替え_1倍.png').crop((110,350,390,550)); b=b.resize((b.width*3,b.height*3),Image.NEAREST); b.save(G+'拡大_塔のまわり_1倍を3倍に拡大.png')
"
