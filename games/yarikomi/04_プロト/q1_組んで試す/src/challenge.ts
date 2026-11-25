// 課題「崖の先の印」（仮。崖の型。07 の課題ではない）。tools/check_challenge.py と同じ盤面。
// 当主は西の高い岩（x=0）の上。崖は x=1〜2、その東は谷底。崖の先 1 マスの宙（3,3）の印に立ち、止まれたら解ける。
export const CHALLENGE = {
  name: '崖の先の印',
  map: [
    '.......',
    '.......',
    '.......',
    '#......',
    '#......',
    '###....',
    '###....',
  ],
  leader: [0, 2] as [number, number],
  goal: [3, 3] as [number, number],
};
