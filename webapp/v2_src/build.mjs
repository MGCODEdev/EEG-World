import * as esbuild from 'esbuild';
import {mkdir, rm, writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';

const outDir = resolve('../static/v2');
const assetsDir = resolve(outDir, 'assets');

await rm(outDir, {recursive: true, force: true});
await mkdir(assetsDir, {recursive: true});

const result = await esbuild.build({
  entryPoints: ['src/main.jsx'],
  bundle: true,
  minify: true,
  sourcemap: false,
  metafile: true,
  outdir: assetsDir,
  entryNames: 'index-[hash]',
  assetNames: 'asset-[hash]',
  loader: {
    '.css': 'css',
    '.js': 'jsx',
    '.jsx': 'jsx',
  },
});

const outputs = Object.keys(result.metafile.outputs);
const jsFile = outputs.find((name) => name.endsWith('.js'));
const cssFile = outputs.find((name) => name.endsWith('.css'));
if (!jsFile) {
  throw new Error('V2 build produced no JavaScript bundle.');
}

await mkdir(resolve(outDir, '.vite'), {recursive: true});
await writeFile(
  resolve(outDir, '.vite', 'manifest.json'),
  JSON.stringify({
    'index.html': {
      file: jsFile.replace(/^.*static\/v2\//, ''),
      css: cssFile ? [cssFile.replace(/^.*static\/v2\//, '')] : [],
    },
  }, null, 2) + '\n',
);
