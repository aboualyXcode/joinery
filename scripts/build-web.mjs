// Bundle the TypeScript client and stylesheet with esbuild, then write
// web/dist/index.html pointing at the content-hashed assets.
import { build, context } from 'esbuild';
import { copyFile, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '..');
const out = path.join(root, 'web', 'dist');
const watch = process.argv.includes('--watch');

async function writeHtml(metafile) {
  const outputs = Object.keys(metafile.outputs).map((file) => path.basename(file));
  const app = outputs.find((file) => file.startsWith('app') && file.endsWith('.js'));
  const styles = outputs.find((file) => file.startsWith('styles') && file.endsWith('.css'));
  if (!app || !styles) throw new Error('esbuild did not produce app.js and styles.css');
  const template = await readFile(path.join(root, 'web', 'index.html'), 'utf8');
  await writeFile(path.join(out, 'index.html'),
    template.replace('/assets/APP', `/assets/${app}`).replace('/assets/STYLES', `/assets/${styles}`));
  await copyFile(path.join(root, 'web', 'static', 'favicon.svg'), path.join(out, 'favicon.svg'));
}

const options = {
  entryPoints: { app: path.join(root, 'web/src/main.ts'), styles: path.join(root, 'web/styles/app.css') },
  outdir: path.join(out, 'assets'),
  bundle: true,
  format: 'esm',
  target: ['es2022'],
  minify: !watch,
  sourcemap: true,
  entryNames: watch ? '[name]' : '[name]-[hash]',
  metafile: true,
  legalComments: 'none',
  logLevel: 'info',
  plugins: [{
    name: 'index-html',
    setup(builder) {
      builder.onEnd(async (result) => {
        if (result.metafile && !result.errors.length) await writeHtml(result.metafile);
      });
    },
  }],
};

await rm(out, { recursive: true, force: true });
await mkdir(path.join(out, 'assets'), { recursive: true });
if (watch) {
  const ctx = await context(options);
  await ctx.watch();
  console.log('Watching web/src and web/styles. Reload the browser after each rebuild.');
} else {
  await build(options);
}
