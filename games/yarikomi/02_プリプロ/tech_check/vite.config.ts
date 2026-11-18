import { defineConfig } from 'vite';
// base を相対にして、どのフォルダに置いても開けるようにする。外部CDNは使わない。
export default defineConfig({ base: './', build: { target: 'es2020' } });
