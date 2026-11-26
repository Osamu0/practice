import { defineConfig } from 'vite';
import { fileURLToPath } from 'node:url';
// パラメータ表.csv（03_仕様）をそのまま読むため、packdefense のフォルダまで読めるようにする。
// base を相対にして、どこに置いても開けるようにする。外部 CDN は使わない。
export default defineConfig({
  base: './',
  server: { host: true, fs: { allow: [fileURLToPath(new URL('../..', import.meta.url))] } },
  build: { target: 'es2022' },
});
