# -*- coding: utf-8 -*-
"""スタイル見本：重厚・案D「鉄と革」の2頭身（アートディレクション第3版）を SVG に書き出す。
game-preprod-art 2026-11-27。
実行：python3 ゲーム/packdefense/02_プリプロ/スタイル見本/作図_重厚_D_2頭身.py
PNG にするには、書き出し_重厚.sh（重厚_D_2頭身 も入れてある）。

決めの数値（英雄。原点＝足もとの中心、1倍の px）
  顔の直径 18（顔の上 -36、あご -18）→ 足もと→顔の上 36 ÷ 18 ＝ 2.0頭身（兜・帽子を除く）
  兜の上まで 48。肩当ての幅 34（兜のつば 29 より広い）。胴の幅 23。ブーツ1つ 11.5×6.5
  ここの英雄6人は「役の影の形だけの仮」。名前・顔・服の中身は外部のデザイナーが決める。
"""
import os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "重厚_D_2頭身.svg")

STYLE = """
text{font-family:-apple-system,'Hiragino Sans','Hiragino Kaku Gothic ProN','Noto Sans CJK JP',sans-serif}
.nf{fill:none}
.lh{stroke:#1C1E24;stroke-width:1.5;stroke-linejoin:round;stroke-linecap:round}
.lm{stroke:#140E16;stroke-width:1.5;stroke-linejoin:round;stroke-linecap:round}
.lt{stroke:#2B2722;stroke-width:2.5;stroke-linejoin:round}
.thin{stroke-width:1}
.s-ul{stroke:#1C1E24;fill:none}.s-ml{stroke:#140E16;fill:none}.s-tl{stroke:#2B2722;fill:none}
.s-grip{stroke:#4A3624;fill:none}.s-brass{stroke:#B8923A;fill:none}.s-wood{stroke:#5C4630;fill:none}
.s-bow{stroke:#6B4F36;fill:none}.s-string{stroke:#E8DFC4;fill:none}
.s-bone{stroke:#9C9484;fill:none}.s-rust{stroke:#7A6A58;fill:none}
.hd{stroke:#5A6069;stroke-width:.8;fill:none;stroke-linecap:round}
.hd2{stroke:#6B4F36;stroke-width:.9;fill:none}
.hd3{stroke:#8A6A4A;stroke-width:.8;fill:none;stroke-dasharray:1.2 1.2}
.brow{stroke:#1C1E24;stroke-width:1.1;fill:none;stroke-linecap:round}
.mouth{stroke:#4A3624;stroke-width:1;fill:none;stroke-linecap:round}
.hglint{stroke:#EEF0F2;stroke-width:1;fill:none;stroke-linecap:round}
.hsteel{fill:#C9CDD2}.hsteelM{fill:#8E949C}.hsteelS{fill:#5A6069}
.hcloth{fill:#3F5C8C}.hclothS{fill:#2A3F63}
.hgreen{fill:#4F6B3A}.hgreenS{fill:#3A5029}
.hrust{fill:#8A4A2E}.hrustS{fill:#66361F}
.hcream{fill:#E8DFC4}.hcreamS{fill:#C8BEA2}
.hleather{fill:#6B4F36}.hleatherS{fill:#4A3624}.hbrass{fill:#B8923A}
.hskin{fill:#D9B596}.hskinS{fill:#B08C70}.hbrim{fill:#7A5E4A;fill-opacity:.55}
.eyeH{fill:#1C1E24}.hhair{fill:#4A3624}.hrivet{fill:#5A6069}
.hsh{fill:#141210;fill-opacity:.45}
.ring1{fill:#2E4A7A;fill-opacity:.35;stroke:#2E4A7A;stroke-width:1.6}
.ring2{fill:#E8DFC4;fill-opacity:.28;stroke:#E8DFC4;stroke-width:1.8}
.ring3{stroke:#E8DFC4;stroke-width:1.2;fill:none}
.msh{fill:#140E16;fill-opacity:.45}
.mrag{fill:#4E4652}.mragS{fill:#3A3340}.mskin{fill:#5A4A5E}.mskinS{fill:#433646}
.eye{fill:#FFD84A}.mteeth{stroke:#D8CFB8;stroke-width:.9;fill:none}.mstud{fill:#8E949C}.mhole{fill:#140E16}
.slime{fill:#7A2A30}.slimeS{fill:#561C22}.slimeH{fill:#A54B53}
.wolf{fill:#4E4A52}.wolfS{fill:#38343C}
.bone{fill:#9C9484}.armor{fill:#2C2830}
.bat{fill:#3E3844}.batB{fill:#4E4652}
.tsh{fill:#141210;fill-opacity:.35}
.st{fill:#B4AC9C}.stS{fill:#8C8476}.stD{fill:#8C8476}.stone2{fill:#A39B8B}
.mort{stroke:#6E675C;stroke-width:1.2;fill:none}
.slit{fill:#1A1714}.door{fill:#4A3826}.iron{stroke:#2B2722;stroke-width:1.2;fill:none}.moss{fill:#55613F}
.flag{fill:#2E4A7A}.flagT{fill:none;stroke:#B8923A;stroke-width:1.2;stroke-linejoin:round}
.pk0{fill:#1C1E24}.pk1{fill:#1E2A45}
.tuft{stroke:#5F6B49;stroke-width:1;fill:none;stroke-linecap:round}
.pebble{fill:#9A9282;stroke:#5E584C;stroke-width:.8}
.roadEdge{stroke:#6E6450;stroke-width:1.5;fill:none}
.hill{fill:#6E7B57}
.tree{fill:#3F4A36;stroke:#262C21;stroke-width:2}.treeL{fill:#56624A}
.rock{fill:#7A766C;stroke:#3A3732;stroke-width:2;stroke-linejoin:round}
.hud{fill:#1E1F24;fill-opacity:.92;stroke:#8C7238;stroke-width:1.5}
.hudIcon{fill:#B4AC9C;stroke:#F2EDE0;stroke-width:1}
.hpbg{fill:#0E0F12}.hp{fill:#5FD38A}
.hudT{fill:#F2EDE0}.hudS{fill:#C9C2B0}
.pauseB{fill:#34363E;stroke:#8C7238;stroke-width:1}.pauseI{fill:#F2EDE0}
.slot{fill:#1E1F24;fill-opacity:.8;stroke:#8C7238;stroke-width:1.5}
.slotE{fill:#1E1F24;fill-opacity:.45;stroke:#C9C2B0;stroke-width:2;stroke-dasharray:5 4}
.slotT{fill:#C9C2B0}
.dmg{fill:#FFFFFF;stroke:#1C1E24;stroke-width:3;paint-order:stroke}
.sheet{fill:#EDEAE3}.cap{fill:#1C1E24}.capS{fill:#555049}
.guide{stroke:#F2EDE0;stroke-width:1;stroke-dasharray:4 3;fill:none;opacity:.8}
.guideT{fill:#F2EDE0;font-size:10px}
"""

# ---------- 英雄の部品（2頭身。原点＝足もとの中心） ----------
PARTS = """
  <g id="base2">
    <ellipse class="hsh" cx="1.5" cy="0.5" rx="10" ry="3"/>
    <ellipse class="ring1" cx="0" cy="0" rx="16" ry="6"/>
    <ellipse class="ring2" cx="0" cy="0" rx="12.5" ry="4.4"/>
    <path class="ring3" d="M0 -6 V-4.4 M0 4.4 V6 M-16 0 H-12.5 M12.5 0 H16"/>
  </g>
  <g id="boots2">
    <path class="hleatherS lh" d="M-10.5 -6.5 H-1.5 V0 H-13 Q-13 -3.5 -10.5 -4 Z"/>
    <path class="hleatherS lh" d="M1.5 -6.5 H10.5 V-4 Q13 -3.5 13 0 H1.5 Z"/>
    <path class="hd2" d="M-10.5 -5 H-1.5 M1.5 -5 H10.5"/>
  </g>
  <g id="plate2">
    <path class="hsteel" d="M-11.5 -20.5 L11.5 -20.5 L10.5 -10.5 L-10.5 -10.5 Z"/>
    <path class="hsteelM" d="M0.5 -20.5 L11.5 -20.5 L10.5 -10.5 L0.5 -10.5 Z"/>
    <path class="hsteelS" d="M-10.8 -13 L10.8 -13 L10.5 -10.5 L-10.5 -10.5 Z"/>
    <path class="hglint" d="M-7.5 -19 L-6.2 -14.5"/>
    <path class="hd" d="M0.5 -20 V-13.5"/>
    <path class="lh nf" d="M-11.5 -20.5 L11.5 -20.5 L10.5 -10.5 L-10.5 -10.5 Z"/>
  </g>
  <g id="jerkin2">
    <path class="hleather" d="M-11 -20.5 L11 -20.5 L10.5 -10.5 L-10.5 -10.5 Z"/>
    <path class="hleatherS" d="M0.5 -20.5 L11 -20.5 L10.5 -10.5 L0.5 -10.5 Z"/>
    <path class="hd3" d="M-1.5 -19.5 V-12.5 M2.5 -19.5 V-12.5"/>
    <path class="lh nf" d="M-11 -20.5 L11 -20.5 L10.5 -10.5 L-10.5 -10.5 Z"/>
  </g>
  <g id="belt2">
    <rect class="hleather lh" x="-11" y="-12.3" width="22" height="3"/>
    <rect class="hbrass lh thin" x="-2" y="-12.8" width="4" height="4"/>
  </g>
  <g id="paulL">
    <path class="hsteel lh" d="M-17 -14.5 Q-18.5 -23.5 -8.5 -23 L-6.5 -19 Q-10.5 -15 -17 -14.5 Z"/>
    <path class="hd" stroke-width="1.1" d="M-16.2 -16.6 Q-12.5 -19.2 -8.2 -19.8"/>
  </g>
  <g id="paulR">
    <path class="hsteelM lh" d="M17 -14.5 Q18.5 -23.5 8.5 -23 L6.5 -19 Q10.5 -15 17 -14.5 Z"/>
    <path class="hd" stroke="#3E434A" stroke-width="1.1" d="M16.2 -16.6 Q12.5 -19.2 8.2 -19.8"/>
  </g>
  <g id="hipL">
    <path class="hsteelS lh" d="M-14 -17 L-19 -12 L-12.5 -8.5 L-10 -10.5 L-14 -12.5 L-12 -15.5 Z"/>
    <circle class="hleatherS lh" cx="-11" cy="-9.6" r="2.8"/>
  </g>
  <g id="armR">
    <path class="hsteelM lh" d="M10 -17 L15.5 -15.5 L15.5 -10.5 L10.5 -11 Z"/>
  </g>
  <g id="face2">
    <path class="hskin" d="M-9 -27 A9 9 0 0 1 9 -27 L8.6 -22.5 Q7.2 -18 0 -18 Q-7.2 -18 -8.6 -22.5 Z"/>
    <path class="hskinS" d="M3 -35.5 A9 9 0 0 1 9 -27 L8.6 -22.5 Q7.2 -18 3 -18 Q7 -26 3 -35.5 Z"/>
    <path class="lh nf" d="M-9 -27 A9 9 0 0 1 9 -27 L8.6 -22.5 Q7.2 -18 0 -18 Q-7.2 -18 -8.6 -22.5 Z"/>
    <rect class="eyeH" x="-4.6" y="-26" width="1.9" height="3"/>
    <rect class="eyeH" x="2.7" y="-26" width="1.9" height="3"/>
    <path class="brow" d="M-6 -27.6 L-2.4 -26.9 M2.4 -26.9 L6 -27.6"/>
    <path class="mouth" d="M-1.8 -20.8 H1.8"/>
  </g>
  <!-- 剣（鍔が原点、刃は上へ。手の籠手つき） -->
  <g id="blade">
    <path class="s-ul" stroke-width="4.2" stroke-linecap="round" d="M0 0 V6"/>
    <path class="s-grip" stroke-width="2.4" stroke-linecap="round" d="M0 0 V6"/>
    <circle class="hbrass lh thin" cx="0" cy="7.2" r="1.9"/>
    <path class="hsteel" d="M-2 0 L-2 -26 L0 -30 L2 -26 L2 0 Z"/>
    <path class="hsteelM" d="M0 0 L0 -30 L2 -26 L2 0 Z"/>
    <path class="hglint" d="M-1 -2 L-1 -25"/>
    <path class="lh nf" d="M-2 0 L-2 -26 L0 -30 L2 -26 L2 0 Z"/>
    <path class="s-ul" stroke-width="4.4" stroke-linecap="round" d="M-5.5 0 H5.5"/>
    <path class="s-brass" stroke-width="2.4" stroke-linecap="round" d="M-5.5 0 H5.5"/>
    <circle class="hsteelS lh" cx="0" cy="2.9" r="3.2"/>
  </g>
"""

def tabard(c, cs, trim=False):
    s = (f'<path class="{c}" d="M-10.5 -11.5 L10.5 -11.5 L12 -5 L5 -6 L0 -4.5 L-5 -6 L-12 -5 Z"/>'
         f'<path class="{cs}" d="M0.5 -11.5 L10.5 -11.5 L12 -5 L5 -6 L0.5 -4.6 Z"/>'
         f'<path class="lh nf" d="M-10.5 -11.5 L10.5 -11.5 L12 -5 L5 -6 L0 -4.5 L-5 -6 L-12 -5 Z"/>')
    if trim:
        s += '<path class="s-brass" stroke-width="1" d="M-11.3 -6.2 L-5 -7 L0 -5.6 L5 -7 L11.3 -6.2"/>'
    return s

def cape(cs, big=False):
    if big:
        return ('<path class="hclothS lh" d="M-12 -21 L-17 -1.5 Q-8 0.5 0 -0.5 Q8 0.5 17 -1.5 L12 -21 Z"/>'
                '<path class="s-brass" stroke-width="1.2" d="M-16.4 -2.6 Q-8 -0.6 0 -1.6 Q8 -0.6 16.4 -2.6"/>')
    return f'<path class="{cs} lh" d="M-12 -20 L-15.5 -4 Q-7 -2 0 -3 Q7 -2 15.5 -4 L12 -20 Z"/>'

HAIR_R = '<path class="hhair lh thin" d="M7.6 -29 Q11.8 -26.5 9.6 -22 Q9 -25.5 7.2 -25.8 Z"/>'
HAIR_L = '<path class="hhair lh thin" d="M-7.6 -29 Q-11.8 -26.5 -9.6 -22 Q-9 -25.5 -7.2 -25.8 Z"/>'

def helm_kettle(tilt=-8):
    # 大きすぎる鉄の兜（つば 29 ＝ 顔の 1.6倍）。剣士の「印」
    return f'''<g transform="rotate({tilt} 0 -31)">
      <path class="hbrim" d="M-8.8 -28.5 H8.8 L8.6 -26.2 H-8.6 Z"/>
      <path class="hsteel" d="M-12.5 -31 Q-13 -47.5 0 -47.8 Q13 -47.5 12.5 -31 Z"/>
      <path class="hsteelM" d="M1 -47.75 Q13 -47.5 12.5 -31 L1 -31 Z"/>
      <path class="hglint" d="M-8.5 -44 Q-9.2 -40 -8.6 -35.5"/>
      <path class="hd" d="M0 -47.5 V-32 M6.5 -43.5 Q8.5 -41.5 8 -39"/>
      <path class="lh nf" d="M-12.5 -31 Q-13 -47.5 0 -47.8 Q13 -47.5 12.5 -31 Z"/>
      <path class="hsteelS" d="M-13 -28.5 L13 -28.5 L12.3 -27.2 L-12.3 -27.2 Z"/>
      <path class="hsteelM" d="M-14.5 -32 L14.5 -32 L13 -28.5 L-13 -28.5 Z"/>
      <path class="hsteel" d="M-14.5 -32 L0 -32 L0 -28.5 L-13 -28.5 Z"/>
      <path class="lh nf" d="M-14.5 -32 L14.5 -32 L13 -28.5 L-13 -28.5 Z M-13 -28.5 L-12.3 -27.2 L12.3 -27.2 L13 -28.5"/>
      <g class="hrivet"><circle cx="-7" cy="-34" r="0.9"/><circle cx="0" cy="-34.2" r="0.9"/><circle cx="7" cy="-34" r="0.9"/></g>
    </g>'''

def helm_crest():
    # エピックの剣士の仮：頬当てと真鍮の飾り（傾けない）
    return '''<g>
      <path class="hbrim" d="M-8.8 -30 H8.8 L8.6 -27.6 H-8.6 Z"/>
      <path class="hbrass lh" d="M-8 -45.5 Q0 -56 8 -45.5 Q0 -48.5 -8 -45.5 Z"/>
      <path class="hsteel" d="M-12 -31 Q-12.5 -47 0 -47.3 Q12.5 -47 12 -31 Z"/>
      <path class="hsteelM" d="M1 -47.25 Q12.5 -47 12 -31 L1 -31 Z"/>
      <path class="hglint" d="M-8 -43.5 Q-8.6 -39.5 -8 -35"/>
      <path class="hd" d="M0 -47 V-33"/>
      <path class="lh nf" d="M-12 -31 Q-12.5 -47 0 -47.3 Q12.5 -47 12 -31 Z"/>
      <path class="hsteelM" d="M-12.8 -32.8 L12.8 -32.8 L12.3 -30 L-12.3 -30 Z"/>
      <path class="hsteel" d="M-12.8 -32.8 L0 -32.8 L0 -30 L-12.3 -30 Z"/>
      <path class="lh nf" d="M-12.8 -32.8 L12.8 -32.8 L12.3 -30 L-12.3 -30 Z"/>
      <path class="hsteel lh" d="M-12.5 -30 L-11.5 -20.5 L-8 -21.8 L-8.8 -30 Z"/>
      <path class="hsteelS lh" d="M12.5 -30 L11.5 -20.5 L8 -21.8 L8.8 -30 Z"/>
      <g class="hrivet"><circle cx="-6" cy="-31.4" r="0.8"/><circle cx="6" cy="-31.4" r="0.8"/></g>
    </g>'''

def helm_cap():
    # 弓使いの仮：小さな鉄の鉢（つばなし）
    return '''<g>
      <path class="hbrim" d="M-8.8 -29.8 H8.8 L8.6 -27.8 H-8.6 Z"/>
      <path class="hsteel" d="M-10.5 -31 Q-11 -44.5 0 -44.8 Q11 -44.5 10.5 -31 Z"/>
      <path class="hsteelM" d="M1 -44.75 Q11 -44.5 10.5 -31 L1 -31 Z"/>
      <path class="hglint" d="M-7 -41.5 Q-7.6 -38.5 -7 -35"/>
      <path class="lh nf" d="M-10.5 -31 Q-11 -44.5 0 -44.8 Q11 -44.5 10.5 -31 Z"/>
      <path class="hsteelM" d="M-11.2 -32.5 L11.2 -32.5 L10.8 -29.8 L-10.8 -29.8 Z"/>
      <path class="hsteel" d="M-11.2 -32.5 L0 -32.5 L0 -29.8 L-10.8 -29.8 Z"/>
      <path class="lh nf" d="M-11.2 -32.5 L11.2 -32.5 L10.8 -29.8 L-10.8 -29.8 Z"/>
    </g>'''

def hat_cream():
    # レアの弓使いの仮：生成りの帽子と真鍮色の羽根
    return '''<g>
      <path class="hbrim" d="M-8.8 -30.5 H8.8 L8.6 -27.8 H-8.6 Z"/>
      <path class="hbrass lh thin" d="M6 -36 Q16 -46 21.5 -53 Q15 -43.5 8.6 -33.6 Z"/>
      <path class="hcream" d="M-9.5 -31 Q-10 -43.5 0 -44 Q10 -43.5 9.5 -31 Z"/>
      <path class="hcreamS" d="M1 -43.95 Q10 -43.5 9.5 -31 L1 -31 Z"/>
      <path class="lh nf" d="M-9.5 -31 Q-10 -43.5 0 -44 Q10 -43.5 9.5 -31 Z"/>
      <rect class="hgreenS" x="-9.7" y="-34.5" width="19.4" height="2.6"/>
      <ellipse class="hcream lh" cx="0" cy="-31" rx="15.5" ry="2.8"/>
      <path class="hcreamS" d="M0.5 -28.25 Q12 -28.6 15.4 -30.6 Q15 -29 0.5 -28.2 Z"/>
    </g>'''

def helm_sallet():
    # 槍兵の仮：先のとがった鉢と細いつば
    return '''<g>
      <path class="hbrim" d="M-8.8 -29.5 H8.8 L8.6 -27.2 H-8.6 Z"/>
      <path class="hsteel" d="M-12.5 -31 Q-11.5 -45 0 -50 Q11.5 -45 12.5 -31 Z"/>
      <path class="hsteelM" d="M1 -49.5 Q11.5 -45 12.5 -31 L1 -31 Z"/>
      <path class="hglint" d="M-8 -41 Q-9.2 -38 -9 -34.5"/>
      <path class="hd" d="M0 -49.5 V-33"/>
      <path class="lh nf" d="M-12.5 -31 Q-11.5 -45 0 -50 Q11.5 -45 12.5 -31 Z"/>
      <path class="hsteelM" d="M-13.5 -32 L13.5 -32 L12.5 -29.5 L-12.5 -29.5 Z"/>
      <path class="hsteel" d="M-13.5 -32 L0 -32 L0 -29.5 L-12.5 -29.5 Z"/>
      <path class="lh nf" d="M-13.5 -32 L13.5 -32 L12.5 -29.5 L-12.5 -29.5 Z"/>
    </g>'''

def helm_round_nasal():
    # 盾の騎士の仮：丸い鉢と鼻当て
    return '''<g>
      <path class="hbrim" d="M-8.8 -29.6 H8.8 L8.6 -27.2 H-8.6 Z"/>
      <path class="hsteel" d="M-12.5 -31 Q-13 -47 0 -47.3 Q13 -47 12.5 -31 Z"/>
      <path class="hsteelM" d="M1 -47.25 Q13 -47 12.5 -31 L1 -31 Z"/>
      <path class="hglint" d="M-8.5 -43.5 Q-9.2 -39.5 -8.6 -35"/>
      <path class="lh nf" d="M-12.5 -31 Q-13 -47 0 -47.3 Q13 -47 12.5 -31 Z"/>
      <path class="hsteelM" d="M-13.2 -32.8 L13.2 -32.8 L12.8 -29.6 L-12.8 -29.6 Z"/>
      <path class="hsteel" d="M-13.2 -32.8 L0 -32.8 L0 -29.6 L-12.8 -29.6 Z"/>
      <path class="lh nf" d="M-13.2 -32.8 L13.2 -32.8 L12.8 -29.6 L-12.8 -29.6 Z"/>
      <path class="hsteelS lh thin" d="M-1.3 -29.8 L1.3 -29.8 L0.9 -23.2 L-0.9 -23.2 Z"/>
      <g class="hrivet"><circle cx="-7" cy="-31.2" r="0.85"/><circle cx="7" cy="-31.2" r="0.85"/></g>
    </g>'''

def bow(top, bot, cx, tips=False):
    s = (f'<path class="s-ul" stroke-width="3.8" stroke-linecap="round" d="M-17 {top} Q{cx} {(top+bot)/2} -17 {bot}"/>'
         f'<path class="s-bow" stroke-width="2.2" stroke-linecap="round" d="M-17 {top} Q{cx} {(top+bot)/2} -17 {bot}"/>'
         f'<path class="s-string" stroke-width=".8" d="M-17 {top} L-17 {bot}"/>')
    if tips:
        s += f'<circle class="hbrass lh thin" cx="-17" cy="{top}" r="1.5"/><circle class="hbrass lh thin" cx="-17" cy="{bot}" r="1.5"/>'
    return s

def bowarm(y):
    return (f'<path class="hleather lh" d="M-9 -20 L-20.5 {y-1.5} L-21.5 {y+2.5} L-10 -15 Z"/>'
            f'<circle class="hleatherS lh" cx="-23.5" cy="{y}" r="3"/>')

QUIVER = ('<path class="hleatherS lh" d="M10 -28 L15 -29.5 L16.5 -13 L11 -12 Z"/>'
          '<path class="s-ul" stroke-width="2.8" stroke-linecap="round" d="M11.5 -28.5 L10.8 -34.5 M13.4 -29 L14.2 -35.3 M15.2 -29.4 L17.6 -34.6"/>'
          '<path class="s-string" stroke-width="1.4" stroke-linecap="round" d="M11.5 -28.5 L10.8 -34.5 M13.4 -29 L14.2 -35.3 M15.2 -29.4 L17.6 -34.6"/>')

def hero(id_, body):
    return f'<g id="{id_}">\n{body}\n</g>'

HEROES = {
 # 剣士・コモン：大きすぎる兜（傾き）、剣が右上、腰に手。藍
 "sword1": "\n".join([
    '<use href="#base2"/>', cape("hclothS"), '<use href="#boots2"/>', tabard("hcloth", "hclothS"),
    '<use href="#plate2"/>', '<use href="#belt2"/>', '<use href="#hipL"/>',
    '<use href="#face2"/>', HAIR_R, helm_kettle(-8),
    '<use href="#paulL"/>', '<use href="#paulR"/>', '<use href="#armR"/>',
    '<use href="#blade" transform="translate(15.5 -12) rotate(30)"/>']),
 # 剣士・エピック：頬当てと真鍮の飾りの兜、真鍮のふちの長いマント、大きな剣
 "sword2": "\n".join([
    '<use href="#base2"/>', cape("hclothS", big=True), '<use href="#boots2"/>', tabard("hcloth", "hclothS", trim=True),
    '<use href="#plate2"/>', '<use href="#belt2"/>', '<use href="#hipL"/>',
    '<use href="#face2"/>', helm_crest(),
    '<use href="#paulL"/>', '<use href="#paulR"/>', '<use href="#armR"/>',
    '<use href="#blade" transform="translate(15.5 -12) rotate(28) scale(1.15)"/>']),
 # 弓使い・コモン：体の横の大きな弧、鉄の小さな鉢、矢筒。苔の緑
 "archer1": "\n".join([
    '<use href="#base2"/>', QUIVER, '<use href="#boots2"/>', tabard("hgreen", "hgreenS"),
    '<use href="#jerkin2"/>', '<use href="#belt2"/>',
    bow(-42, -2, -31), bowarm(-22),
    '<use href="#face2"/>', HAIR_L, HAIR_R, helm_cap(),
    '<use href="#paulR"/>', '<path class="hleatherS lh" d="M10 -17 L15 -15.5 L15 -10.5 L10.5 -11 Z"/>',
    '<circle class="hleatherS lh" cx="14" cy="-9.5" r="3"/>']),
 # 弓使い・レア：生成りの帽子と羽根、長い弓（真鍮の先）、緑のマント
 "archer2": "\n".join([
    '<use href="#base2"/>', cape("hgreenS"), QUIVER, '<use href="#boots2"/>', tabard("hgreen", "hgreenS"),
    '<use href="#jerkin2"/>', '<use href="#belt2"/>',
    bow(-46, 0, -32, tips=True), bowarm(-23),
    '<use href="#face2"/>', HAIR_R, hat_cream(),
    '<use href="#paulR"/>', '<path class="hleatherS lh" d="M10 -17 L15 -15.5 L15 -10.5 L10.5 -11 Z"/>',
    '<circle class="hleatherS lh" cx="14" cy="-9.5" r="3"/>']),
 # 盾の騎士・コモン：体の前の大きな四角い盾（いちばん横に広い）。鋼＋藍
 "shield1": "\n".join([
    '<use href="#base2"/>', '<use href="#boots2"/>', tabard("hcloth", "hclothS"),
    '<use href="#plate2"/>', '<use href="#belt2"/>',
    '<use href="#face2"/>', helm_round_nasal(),
    '<use href="#paulL"/>', '<use href="#paulR"/>', '<use href="#armR"/>',
    '<use href="#blade" transform="translate(15 -12) rotate(12) scale(.62)"/>',
    '<rect class="hsteelS lh thin" x="0.6" y="-18.6" width="2.4" height="17"/>',
    '<rect class="hsteelM lh" x="-22.5" y="-20" width="23.5" height="19.5" rx="2.5"/>',
    '<rect class="hcloth" x="-19.5" y="-17" width="17.5" height="13.5" rx="1.5"/>',
    '<path class="hclothS" d="M-10.75 -17 H-3.5 Q-2 -17 -2 -15.5 V-5 Q-2 -3.5 -3.5 -3.5 H-10.75 Z"/>',
    '<path class="hglint" d="M-20.5 -18.2 L-9 -18.2"/>',
    '<circle class="hbrass lh thin" cx="-10.75" cy="-10.25" r="3.2"/>',
    '<g class="hrivet"><circle cx="-20.6" cy="-2.3" r=".9"/><circle cx="-1" cy="-2.3" r=".9"/></g>']),
 # 槍兵・レア：いちばん背の高い縦の線（槍）、とがった鉢。錆びた赤茶
 "spear1": "\n".join([
    '<use href="#base2"/>', '<use href="#boots2"/>', tabard("hrust", "hrustS"),
    '<use href="#plate2"/>', '<use href="#belt2"/>', '<use href="#hipL"/>',
    '<use href="#face2"/>', HAIR_L, helm_sallet(),
    '<use href="#paulL"/>', '<use href="#paulR"/>', '<use href="#armR"/>',
    '<path class="s-ul" stroke-width="3.6" stroke-linecap="round" d="M15 3 V-55"/>',
    '<path class="s-wood" stroke-width="1.9" stroke-linecap="round" d="M15 3 V-55"/>',
    '<path class="hsteel" d="M15 -66 L18.2 -58.5 L15 -54.5 L11.8 -58.5 Z"/>',
    '<path class="hsteelM" d="M15 -66 L18.2 -58.5 L15 -54.5 Z"/>',
    '<path class="lh nf" d="M15 -66 L18.2 -58.5 L15 -54.5 L11.8 -58.5 Z"/>',
    '<rect class="hbrass lh thin" x="13.6" y="-55.5" width="2.8" height="2.2"/>',
    '<circle class="hsteelS lh" cx="15" cy="-11" r="3.2"/>']),
}

# ---------- 魔物（重厚_D と同じ図形。骸骨だけ2頭身相当に描き直し） ----------
MONSTERS = """
  <g id="goblin">
    <path class="msh" d="M-13 0 L-9 -3 L-5 1 L-1 -3 L3 1 L7 -3 L11 1 L13 0 L9 3.5 L0 4.5 L-9 3.5 Z"/>
    <path class="s-ml" stroke-width="6" stroke-linecap="round" d="M8 -10 L17 -30"/>
    <path class="s-wood" stroke-width="3.6" stroke-linecap="round" d="M8 -10 L17 -30"/>
    <g class="mstud"><circle cx="14.8" cy="-25" r="0.9"/><circle cx="16.4" cy="-28.2" r="0.9"/></g>
    <path class="s-ml" stroke-width="3.2" stroke-linecap="round" d="M-5 -6 L-6 0 M4 -6 L5 0"/>
    <path class="mrag" d="M-10 -2 L-11 -15 Q-2 -25 9 -16 L10 -2 L6 -5 L3 -1 L-1 -5 L-4 -1 L-7 -5 Z"/>
    <path class="mragS" d="M1 -21.5 Q6 -20 9 -16 L10 -2 L6 -5 L3 -1 L1 -3 Z"/>
    <path class="lm nf" d="M-10 -2 L-11 -15 Q-2 -25 9 -16 L10 -2 L6 -5 L3 -1 L-1 -5 L-4 -1 L-7 -5 Z"/>
    <path class="mskinS lm" d="M6.5 -15 L10 -10.5 L8 -9 L5 -12.5 Z"/>
    <path class="mskin lm" d="M-8 -24 L-21 -29 L-10 -18 Z"/>
    <path class="mskin lm" d="M5 -24 L18 -29 L7 -18 Z"/>
    <circle class="mskin" cx="-1.5" cy="-21" r="8"/>
    <path class="mskinS" d="M0.5 -28.75 A8 8 0 0 1 0.5 -13.25 A10 10 0 0 0 0.5 -28.75 Z"/>
    <circle class="lm nf" cx="-1.5" cy="-21" r="8"/>
    <path class="s-ml" stroke-width="1.4" stroke-linecap="round" d="M-7 -24 L-3 -22.5 M4 -24 L0 -22.5"/>
    <circle class="eye" cx="-4.5" cy="-20.5" r="1.9"/>
    <circle class="eye" cx="1.5" cy="-20.5" r="1.9"/>
    <path class="mteeth" d="M-5 -16.5 L-4 -15 L-3 -16.5 L-2 -15 L-1 -16.5 L0 -15 L1 -16.5"/>
  </g>
  <g id="slime">
    <path class="msh" d="M-15 1 L-10 -2 L-6 2 L-2 -2 L2 2 L6 -2 L10 2 L15 1 L10 4 L0 5 L-10 4 Z"/>
    <path class="slime" d="M-16 0 C-18 -16 -8 -28 0 -28 C8 -28 18 -16 16 0 Q8 -4 0 0 Q-8 -4 -16 0 Z"/>
    <path class="slimeS" d="M3 -27.6 C11 -25 18 -15 16 0 Q8 -4 0 0 Q9 -11 3 -27.6 Z"/>
    <ellipse class="slimeH" cx="-7" cy="-20" rx="3.6" ry="2" transform="rotate(-35 -7 -20)"/>
    <circle class="slimeS" cx="7" cy="-6" r="1.6"/><circle class="slimeS" cx="10" cy="-10" r="1"/>
    <path class="lm nf" d="M-16 0 C-18 -16 -8 -28 0 -28 C8 -28 18 -16 16 0 Q8 -4 0 0 Q-8 -4 -16 0 Z"/>
    <path class="s-ml" stroke-width="1.6" stroke-linecap="round" d="M-8.5 -17 L-3 -15 M8.5 -17 L3 -15"/>
    <circle class="eye" cx="-5" cy="-12.5" r="2.5"/>
    <circle class="eye" cx="5" cy="-12.5" r="2.5"/>
  </g>
  <g id="swarm">
    <use href="#slime" transform="translate(-6 -7) scale(0.45)"/>
    <use href="#slime" transform="translate(8 -1) scale(0.45)"/>
    <use href="#slime" transform="translate(-2 7) scale(0.45)"/>
  </g>
  <g id="wolf">
    <path class="msh" d="M-18 0 L-13 -2.5 L-8 1 L-3 -2.5 L2 1 L7 -2.5 L12 1 L17 -1 L21 1 L15 3.5 L0 4.5 L-14 3.5 Z"/>
    <path class="s-ml" stroke-width="3.4" stroke-linecap="round" d="M-10 -8 L-11 0 M-4 -8 L-4.5 0 M6 -8 L6.5 0 M11 -8 L12.5 0"/>
    <path class="wolfS lm" d="M-13 -13 L-25 -20 L-21 -14 L-24 -12 L-14 -9 Z"/>
    <path class="wolf" d="M-15 -11 Q-14 -18 -4 -18 L8 -19 Q14 -19 15 -13 L13 -7 L-13 -7 Z"/>
    <path class="wolfS" d="M-14 -9.5 L13.6 -9.5 L13 -7 L-13 -7 Z"/>
    <path class="lm nf" d="M-15 -11 Q-14 -18 -4 -18 L8 -19 Q14 -19 15 -13 L13 -7 L-13 -7 Z"/>
    <path class="s-ml" stroke-width="1" d="M-9 -17 L-7 -19.5 L-5 -17.5 L-3 -20 L-1 -18"/>
    <path class="wolfS lm" d="M15 -19 L17.5 -26 L19.5 -19.5 Z"/>
    <path class="wolf lm" d="M9 -17 L12.5 -25.5 L16 -19 L19 -19.5 L27 -14.5 L25 -11.5 L15 -10 Z"/>
    <circle class="eye" cx="19" cy="-16" r="1.5"/>
    <path class="mteeth" d="M21 -12.3 L22 -11 L23 -12.4"/>
  </g>
  <!-- 骸骨の兵士：2頭身相当に描き直し（頭蓋＋兜 18 ÷ 高さ 36）。骨は 150 まで、暗い兜と鎧 -->
  <g id="skel">
    <path class="msh" d="M-12 0 L-8 -2.5 L-4 1 L0 -2.5 L4 1 L8 -2.5 L12 0 L8 3 L0 4 L-8 3 Z"/>
    <path class="s-ml" stroke-width="3.4" stroke-linecap="round" d="M-3.5 -9 L-5 0 M3.5 -9 L5 0 M9.5 -10.5 L14 -30"/>
    <path class="s-bone" stroke-width="1.5" stroke-linecap="round" d="M-3.5 -9 L-5 0 M3.5 -9 L5 0"/>
    <path class="s-rust" stroke-width="1.8" stroke-linecap="round" d="M9.5 -10.5 L14 -30"/>
    <path class="s-ml" stroke-width="3.2" stroke-linecap="round" d="M-7 -18 L-10.5 -10 M7 -18 L9.5 -10.5"/>
    <path class="s-bone" stroke-width="1.4" stroke-linecap="round" d="M-7 -18 L-10.5 -10 M7 -18 L9.5 -10.5"/>
    <path class="armor lm" d="M-8 -19.5 L8 -19.5 L6.5 -9 L-6.5 -9 Z"/>
    <path class="s-bone" stroke-width="1" d="M-4.5 -16.5 H4.5 M-4 -13.5 H4"/>
    <rect class="bone lm" x="-7" y="-30" width="14" height="12.5" rx="4"/>
    <path class="s-ml" stroke-width="0.8" d="M-3.5 -20 V-18 M0 -20 V-18 M3.5 -20 V-18"/>
    <path class="armor lm" d="M-8.5 -26 L-8.5 -36 L8.5 -36 L8.5 -26 L4.5 -27.5 L-4.5 -27.5 Z"/>
    <circle class="mhole" cx="-3" cy="-23.3" r="2.3"/><circle class="mhole" cx="3" cy="-23.3" r="2.3"/>
    <circle class="eye" cx="-3" cy="-23.3" r="1.3"/><circle class="eye" cx="3" cy="-23.3" r="1.3"/>
  </g>
  <g id="bat">
    <path class="msh" d="M-8 0 L-5 -2 L-2 1 L1 -2 L4 1 L8 0 L4 2.5 L-4 2.5 Z"/>
    <path class="bat lm" d="M-17 -25 L-10 -31 L-7 -27 L-3 -31 L0 -28 L3 -31 L7 -27 L10 -31 L17 -25 L9 -23 L6 -20 L3 -23 L0 -20.5 L-3 -23 L-6 -20 L-9 -23 Z"/>
    <circle class="batB lm" cx="0" cy="-25.5" r="4.5"/>
    <path class="batB lm" d="M-3 -29 L-2.5 -32.5 L-1 -29.5 Z M3 -29 L2.5 -32.5 L1 -29.5 Z"/>
    <circle class="eye" cx="-1.7" cy="-26" r="1.1"/><circle class="eye" cx="1.7" cy="-26" r="1.1"/>
  </g>
  <g id="tower">
    <ellipse class="tsh" cx="8" cy="1" rx="40" ry="9"/>
    <rect class="st" x="-30" y="-74" width="60" height="74"/>
    <g class="stone2"><rect x="-26" y="-60" width="10" height="9"/><rect x="-6" y="-48" width="12" height="9"/><rect x="-24" y="-36" width="9" height="9"/><rect x="-2" y="-72" width="9" height="9"/></g>
    <rect class="stS" x="12" y="-74" width="18" height="74"/>
    <rect class="stD" x="-30" y="-13" width="60" height="13"/>
    <path class="mort" d="M-30 -62 H30 M-30 -50 H30 M-30 -38 H30 M-30 -26 H30 M-30 -13 H30 M-18 -74 V-62 M4 -74 V-62 M22 -74 V-62 M-8 -62 V-50 M14 -62 V-50 M-22 -50 V-38 M2 -50 V-38 M20 -50 V-38 M-12 -38 V-26 M10 -38 V-26 M-20 -26 V-13 M16 -26 V-13 M-14 -13 V0 M18 -13 V0"/>
    <rect class="lt nf" x="-30" y="-74" width="60" height="74"/>
    <rect class="slit" x="-3" y="-64" width="6" height="15" rx="3"/>
    <path class="door lt" d="M-9 0 V-17 Q0 -28 9 -17 V0 Z"/>
    <path class="iron" d="M-9 -12 H9 M-9 -5 H9 M0 -25 V0"/>
    <path class="moss" d="M-30 0 Q-26 -6 -20 -3 Q-16 -7 -12 -2 L-12 0 Z M14 0 Q18 -5 23 -2 Q27 -6 30 -1 L30 0 Z"/>
    <rect class="st lt" x="-34" y="-91" width="68" height="17"/>
    <rect class="stS" x="14" y="-89.5" width="18.8" height="14.3"/>
    <path class="mort" d="M-34 -82 H34"/>
    <path class="st lt" d="M-34 -91 V-102 H-23 V-91 Z M-15 -91 V-102 H-4 V-91 Z M4 -91 V-102 H15 V-91 Z M23 -91 V-102 H34 V-91 Z"/>
    <path class="s-tl" stroke-width="2" d="M0 -91 V-134"/>
    <path class="flag" d="M1 -133 L25 -127 L19 -123.5 L25 -120 L1 -118 Z"/>
    <path class="flagT" d="M1 -133 L25 -127 L19 -123.5 L25 -120 L1 -118 Z"/>
  </g>
  <g id="pack">
    <rect class="pk0" x="-14.5" y="-39.5" width="29" height="41" rx="4"/>
    <rect class="pk1" x="-13" y="-38" width="26" height="38" rx="3" stroke="#4FA3FF" stroke-width="3"/>
    <path d="M-13 -34 L-10 -37 L-7 -34 L-4 -37 L-1 -34 L2 -37 L5 -34 L8 -37 L11 -34 L13 -36" stroke="#4FA3FF" stroke-width="2" fill="none"/>
    <path d="M0 -26 L2.5 -20.5 L8 -20 L3.8 -16.2 L5 -11 L0 -13.8 L-5 -11 L-3.8 -16.2 L-8 -20 L-2.5 -20.5 Z" fill="#FFFFFF"/>
    <circle cx="-4" cy="-5" r="2" fill="#FFFFFF"/><circle cx="4" cy="-5" r="2" fill="#FFFFFF"/>
  </g>
"""

SCREEN = """
  <g id="screen" font-family="-apple-system,'Hiragino Sans','Hiragino Kaku Gothic ProN','Noto Sans CJK JP',sans-serif">
    <rect width="390" height="844" fill="url(#tile)"/>
    <path class="tuft" d="M30 230 l2 -5 l2 5 l2 -4 M84 282 l2 -5 l2 5 l2 -4 M140 250 l2 -5 l2 5 l2 -4 M250 180 l2 -5 l2 5 l2 -4 M300 300 l2 -5 l2 5 l2 -4 M352 250 l2 -5 l2 5 l2 -4 M60 560 l2 -5 l2 5 l2 -4 M120 620 l2 -5 l2 5 l2 -4 M250 560 l2 -5 l2 5 l2 -4 M330 540 l2 -5 l2 5 l2 -4 M280 700 l2 -5 l2 5 l2 -4 M90 700 l2 -5 l2 5 l2 -4 M40 350 l2 -5 l2 5 l2 -4 M345 380 l2 -5 l2 5 l2 -4 M140 470 l2 -5 l2 5 l2 -4 M240 620 l2 -5 l2 5 l2 -4 M360 640 l2 -5 l2 5 l2 -4 M100 170 l2 -5 l2 5 l2 -4 M300 160 l2 -5 l2 5 l2 -4 M150 330 l2 -5 l2 5 l2 -4"/>
    <g class="pebble"><ellipse cx="64" cy="260" rx="2.4" ry="1.5"/><ellipse cx="320" cy="330" rx="2.4" ry="1.5"/><ellipse cx="110" cy="600" rx="2" ry="1.3"/><ellipse cx="262" cy="690" rx="2.4" ry="1.5"/><ellipse cx="352" cy="500" rx="2" ry="1.3"/><ellipse cx="40" cy="500" rx="2.4" ry="1.5"/><ellipse cx="236" cy="330" rx="2" ry="1.3"/></g>
    <rect x="173" y="0" width="44" height="844" fill="url(#road)"/>
    <rect x="0" y="408" width="390" height="44" fill="url(#road)"/>
    <path class="roadEdge" d="M173 0 V408 M217 0 V408 M173 452 V844 M217 452 V844 M0 408 H173 M217 408 H390 M0 452 H173 M217 452 H390"/>
    <ellipse class="hill" cx="195" cy="448" rx="64" ry="27"/>
    <g class="tree">
      <circle cx="22" cy="126" r="16"/><circle cx="46" cy="118" r="14"/><circle cx="34" cy="144" r="15"/>
      <circle cx="368" cy="124" r="16"/><circle cx="344" cy="132" r="14"/><circle cx="364" cy="150" r="15"/>
      <circle cx="20" cy="800" r="16"/><circle cx="44" cy="814" r="14"/><circle cx="24" cy="830" r="15"/>
      <circle cx="368" cy="800" r="16"/><circle cx="346" cy="816" r="14"/><circle cx="370" cy="830" r="15"/>
    </g>
    <g class="treeL"><circle cx="17" cy="121" r="5"/><circle cx="363" cy="119" r="5"/><circle cx="15" cy="795" r="5"/><circle cx="363" cy="795" r="5"/></g>
    <path class="rock" d="M4 400 L14 390 L28 394 L30 404 L6 406 Z"/>
    <path class="rock" d="M362 472 L372 462 L386 466 L388 478 L364 480 Z"/>
    <use href="#bat" x="112" y="196"/>
    <use href="#goblin" x="232" y="226"/>
    <use href="#goblin" x="195" y="262"/>
    <rect x="90" y="104" width="30" height="240" fill="url(#beam)"/>
    <ellipse cx="105" cy="344" rx="30" ry="10" fill="url(#landglow)"/>
    <use href="#pack" x="105" y="344"/>
    <g stroke="#FFFFFF" stroke-width="2" stroke-linecap="round"><path d="M82 312 L78 308"/><path d="M128 312 L132 308"/><path d="M84 336 L79 338"/><path d="M126 336 L131 338"/></g>
    <use href="#sword1" x="270" y="368"/>
    <use href="#wolf" x="66" y="444"/>
    <use href="#tower" x="195" y="452"/>
    <use href="#slime" x="310" y="454"/>
    <use href="#shield1" x="252" y="486"/>
    <use href="#archer1" x="132" y="526"/>
    <use href="#swarm" x="302" y="607"/>
    <use href="#skel" x="195" y="640"/>
    <path d="M290 440 Q305 424 326 431" stroke="#FFFFFF" stroke-opacity="0.85" stroke-width="3" fill="none" stroke-linecap="round"/>
    <circle cx="338" cy="466" r="5" fill="#FFD24A" stroke="#8A6A10" stroke-width="1.5"/>
    <text class="dmg" x="318" y="404" font-size="15" font-weight="700">1.2万</text>
    <ellipse cx="308" cy="494" rx="20" ry="24" fill="#1B2233" fill-opacity="0.18"/>
    <path d="M308 468 V476" stroke="#FFFFFF" stroke-width="2" stroke-dasharray="3 3"/>
    <circle cx="308" cy="438" r="28" fill="#FFFFFF" fill-opacity="0.12" stroke="#1B2233" stroke-opacity="0.55" stroke-width="4.5"/>
    <circle cx="308" cy="438" r="28" fill="none" stroke="#FFFFFF" stroke-width="2.5"/>
    <path d="M6 430 L24 417 L24 443 Z" fill="#FF5A1F" stroke="#1B2233" stroke-width="2" stroke-linejoin="round"/>
    <text x="17.5" y="436" font-size="13" font-weight="800" fill="#FFFFFF" text-anchor="middle">!</text>
    <rect class="hud" x="8" y="52" width="374" height="52" rx="8"/>
    <rect class="hudIcon" x="18" y="66" width="10" height="16"/>
    <rect class="hpbg" x="34" y="71" width="100" height="10" rx="3"/>
    <rect class="hp" x="35" y="72" width="70" height="8" rx="2"/>
    <text class="hudT" x="140" y="82" font-size="15" font-weight="700">720</text>
    <text class="hudS" x="180" y="72" font-size="12">ウェーブ</text>
    <text class="hudT" x="180" y="95" font-size="20" font-weight="700">12</text>
    <circle cx="242" cy="79" r="8" fill="#FFD24A" stroke="#8A6A10" stroke-width="1.5"/>
    <text class="hudT" x="255" y="85" font-size="17" font-weight="700">1.2万</text>
    <rect class="pauseB" x="330" y="56" width="44" height="44" rx="6"/>
    <rect class="pauseI" x="344" y="68" width="5" height="20" rx="1"/>
    <rect class="pauseI" x="355" y="68" width="5" height="20" rx="1"/>
    <rect class="slot" x="119" y="692" width="68" height="90" rx="6"/>
    <rect x="123" y="696" width="60" height="82" rx="4" fill="#3A2418" stroke="#FFC23A" stroke-width="3"/>
    <path d="M141 740 Q132 748 128 756 Q140 752 146 744 Z" fill="#FF7A2A" stroke="#1B2233" stroke-width="1.5" stroke-linejoin="round"/>
    <circle cx="153" cy="728" r="13" fill="#FF7A2A" stroke="#1B2233" stroke-width="2"/>
    <circle cx="150" cy="725" r="6" fill="#FFE14D"/>
    <text x="153" y="766" font-size="12" font-weight="700" fill="#FFFFFF" text-anchor="middle">火の玉</text>
    <g fill="#FFC23A"><circle cx="141" cy="773" r="1.8"/><circle cx="149" cy="773" r="1.8"/><circle cx="157" cy="773" r="1.8"/><circle cx="165" cy="773" r="1.8"/></g>
    <rect class="slotE" x="203" y="692" width="68" height="90" rx="6"/>
    <text class="slotT" x="237" y="742" font-size="12" text-anchor="middle">空き</text>
    <rect x="128" y="831" width="134" height="5" rx="2.5" fill="#111111" fill-opacity="0.55"/>
  </g>
"""

# 並べ図の顔ぶれ（縦切り：パラメータ表 6章、魔物.md の縦切り4種）と、1倍での左右の広がり
LINEUP = [
    ("sword1", "剣士", "sword1・コモン", -17.5, 31),
    ("sword2", "剣士", "sword2・エピック", -17.5, 33.5),
    ("archer1", "弓使い", "archer1・コモン", -27, 18),
    ("archer2", "弓使い", "archer2・レア", -27, 22),
    ("shield1", "盾の騎士", "shield1・コモン", -23.5, 18),
    ("spear1", "槍兵", "spear1・レア", -17.5, 18.5),
    ("slime", "スライム", "slime・ふつう", -16.5, 16.5),
    ("wolf", "オオカミ", "wolf・速い", -25.5, 27.5),
    ("skel", "骸骨の兵士", "skeleton・硬い", -12.5, 15),
    ("swarm", "群れ", "swarm・群れ", -14, 16),
]

def layout(scale, left, gap, mgap):
    xs, r = [], left
    for i, (_, _, _, l, rr) in enumerate(LINEUP):
        g = mgap if i == 6 else (0 if i == 0 else gap)
        c = r + g - l * scale
        xs.append(c)
        r = c + rr * scale
    return xs, r


def build():
    W, H = 1200, 1300
    out = []
    a = out.append
    a(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">')
    a('<!-- スタイル見本：重厚・案D「鉄と革」の2頭身（アートディレクション第3版）。game-preprod-art 2026-11-27。\n'
      '     作図_重厚_D_2頭身.py で書き出したもの。直すときは .py を直して書き出し直す。\n'
      '     2頭身（兜・帽子を除く）：顔18、足もと→顔の上36。兜の上まで48。縁・色の段・光は 重厚_D と同じ。\n'
      '     英雄6人は役の影の形だけの仮（名前・顔・服の中身は外部のデザイナーが決める）。 -->')
    a('<style>' + STYLE + '</style>')
    a('<defs>')
    a('''  <pattern id="tile" width="64" height="64" patternUnits="userSpaceOnUse">
    <rect width="64" height="64" fill="#7F8C64"/><rect width="32" height="32" fill="#7A875F"/><rect x="32" y="32" width="32" height="32" fill="#7A875F"/>
  </pattern>
  <pattern id="road" width="22" height="14" patternUnits="userSpaceOnUse">
    <rect width="22" height="14" fill="#A39377"/><path d="M0 7 H22 M8 0 V7 M19 7 V14" stroke="#857762" stroke-width="1"/>
  </pattern>
  <linearGradient id="beam" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#FFFFFF" stop-opacity="0"/><stop offset="0.6" stop-color="#CFE4FF" stop-opacity="0.5"/><stop offset="1" stop-color="#FFFFFF" stop-opacity="0.85"/>
  </linearGradient>
  <radialGradient id="landglow"><stop offset="0" stop-color="#4FA3FF" stop-opacity="0.65"/><stop offset="1" stop-color="#4FA3FF" stop-opacity="0"/></radialGradient>
  <clipPath id="clipS"><rect width="390" height="844"/></clipPath>
  <filter id="gray" color-interpolation-filters="sRGB"><feColorMatrix type="saturate" values="0"/></filter>
  <filter id="sil" color-interpolation-filters="sRGB"><feColorMatrix type="matrix" values="0 0 0 0 0.11  0 0 0 0 0.11  0 0 0 0 0.13  0 0 0 1 0"/></filter>''')
    a(PARTS)
    for k, v in HEROES.items():
        a(hero(k, v))
    a(MONSTERS)
    a(SCREEN)
    a('</defs>')

    a(f'<rect class="sheet" width="{W}" height="{H}"/>')
    a('<text class="cap" x="16" y="22" font-size="15" font-weight="700">重厚・案D「鉄と革」の2頭身（第3版）　2頭身（兜を除く）・英雄の高さ48・肩は兜より広い・素材ごとの暗い縁取り1.5・色3段＋金属の照り</text>')
    a('<text class="capS" x="16" y="40" font-size="11.5">左：色（iPhone 縦 390×844、1倍）　中：白黒（彩度0）　右：4倍・3倍・1倍。下：縦切りの顔ぶれの並べ図（英雄6は役の影の形だけの仮、魔物4と同じ比率）</text>')
    a('<g transform="translate(16 48)"><g clip-path="url(#clipS)"><use href="#screen"/></g></g>')
    a('<g transform="translate(422 48)" filter="url(#gray)"><g clip-path="url(#clipS)"><use href="#screen"/></g></g>')

    # 右：4倍・3倍・1倍
    a('<g transform="translate(828 48)">')
    a('<rect width="308" height="844" fill="url(#tile)"/>')
    a('<rect x="0" y="0" width="308" height="26" fill="#1E1F24" fill-opacity="0.85"/>')
    a('<text x="8" y="18" font-size="12" fill="#F2EDE0">剣士 4倍（足もと y=270）。紋の輪 32×12</text>')
    fx, fy, s = 104, 270, 4
    for v, lab in [(48, "兜の上 48"), (36, "顔の上 36"), (18, "あご 18")]:
        y = fy - v * s
        a(f'<path class="guide" d="M8 {y} H300"/><text class="guideT" x="248" y="{y-3}">{lab}</text>')
    a(f'<text class="guideT" x="248" y="{fy-3}">足もと 0</text>')
    a(f'<use href="#sword1" transform="translate({fx} {fy}) scale({s})"/>')
    a('<rect x="0" y="330" width="308" height="22" fill="#1E1F24" fill-opacity="0.85"/>')
    a('<text x="8" y="346" font-size="12" fill="#F2EDE0">魔物 3倍：ゴブリン・スライム／オオカミ・骸骨</text>')
    a('<use href="#goblin" transform="translate(80 470) scale(3)"/>')
    a('<use href="#slime" transform="translate(228 470) scale(3)"/>')
    a('<use href="#wolf" transform="translate(95 612) scale(3)"/>')
    a('<use href="#skel" transform="translate(245 612) scale(3)"/>')
    a('<rect x="0" y="650" width="308" height="22" fill="#1E1F24" fill-opacity="0.85"/>')
    a('<text x="8" y="666" font-size="12" fill="#F2EDE0">1倍（ゲームの大きさ）</text>')
    for href, x in [("sword1", 30), ("shield1", 74), ("goblin", 120), ("slime", 162), ("wolf", 212), ("skel", 270)]:
        a(f'<use href="#{href}" x="{x}" y="740"/>')
    a('<rect x="0" y="770" width="308" height="74" fill="#1E1F24" fill-opacity="0.85"/>')
    for i, t in enumerate(["頭身：顔18、足もと→顔の上36 ＝ 2.0（兜を除く）",
                           "高さ：兜の上48、肩当ての幅34＞兜のつば29、輪58",
                           "縁：英雄 #1C1E24・魔物 #140E16 1.5、塔 2.5",
                           "目は小さな縦の点2×3、眉は内へ下げる、つばの影"]):
        a(f'<text x="8" y="{788+16*i}" font-size="11" fill="#F2EDE0">{t}</text>')
    a('</g>')

    # 下：並べ図
    Y0 = 904
    a(f'<text class="cap" x="16" y="{Y0+16}" font-size="14" font-weight="700">縦切りの顔ぶれ（英雄6・魔物4）を同じ比率で並べる　2.5倍</text>')
    a(f'<text class="capS" x="520" y="{Y0+16}" font-size="11">英雄は役の影の形だけの仮（依頼書の添付用）。名前・顔・服の中身はデザイナーが決める。点線は兜の上48・顔の上36・あご18</text>')
    s1, feet1 = 2.5, Y0 + 210
    xs, r = layout(s1, 44, 9, 18)
    assert r < 1184, r
    a(f'<rect x="16" y="{Y0+26}" width="1168" height="208" fill="url(#tile)"/>')
    hero_r = xs[5] + LINEUP[5][4] * s1 + 4
    for v in (48, 36, 18):
        y = feet1 - v * s1
        a(f'<path class="guide" d="M42 {y} H{hero_r:.1f}"/><text class="guideT" x="22" y="{y+3.5}">{v}</text>')
    a(f'<text class="guideT" x="22" y="{feet1+3.5}">0</text>')
    a(f'<path d="M{(hero_r+xs[6]+LINEUP[6][3]*s1)/2:.1f} {Y0+30} V{Y0+230}" stroke="#F2EDE0" stroke-width="1" opacity=".5"/>')
    for (href, role, lab, l, rr), x in zip(LINEUP, xs):
        a(f'<use href="#{href}" transform="translate({x:.1f} {feet1}) scale({s1})"/>')
        a(f'<rect x="{x-44:.1f}" y="{feet1+18}" width="88" height="14" rx="3" fill="#1E1F24" fill-opacity=".8"/>')
        a(f'<text x="{x:.1f}" y="{feet1+28.5}" font-size="9" fill="#F2EDE0" text-anchor="middle">{lab}</text>')

    Y2 = Y0 + 250
    a(f'<text class="capS" x="16" y="{Y2+12}" font-size="11.5">1倍（ゲームの大きさ）</text>')
    a(f'<text class="capS" x="600" y="{Y2+12}" font-size="11.5">影だけ（1倍。輪と落ち影は薄く残る）</text>')
    feet2 = Y2 + 92
    a(f'<rect x="16" y="{Y2+20}" width="560" height="90" fill="url(#tile)"/>')
    xs2, _ = layout(1, 40, 10, 20)
    for (href, *_), x in zip(LINEUP, xs2):
        a(f'<use href="#{href}" x="{x:.1f}" y="{feet2}"/>')
    a('<g filter="url(#sil)">')
    for (href, *_), x in zip(LINEUP, xs2):
        a(f'<use href="#{href}" x="{x+560:.1f}" y="{feet2}"/>')
    a('</g>')
    a(f'<text class="capS" x="16" y="{H-8}" font-size="11">英雄の高さ（武器を除く）：剣士48・エピックの剣士 飾りまで54・弓使い45・帽子の弓使い 羽根まで53・盾の騎士47・槍兵50（槍の先66）。魔物は見た目を変えない（骸骨だけ頭を大きく描き直し、高さ36）</text>')
    a('</svg>')
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print(OUT, xs, r)

if __name__ == "__main__":
    build()
