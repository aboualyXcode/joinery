// Bundle the TypeScript client and stylesheet with esbuild, then write
// web/dist/index.html pointing at the content-hashed assets.
import { build, context } from 'esbuild';
import { copyFile, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '..');
const watch = process.argv.includes('--watch');
// --static builds the published preview: relative URLs and recorded responses.
const isStatic = process.argv.includes('--static');
const out = path.join(root, 'web', isStatic ? 'site' : 'dist');
const base = isStatic ? 'assets/' : '/assets/';

async function writeHtml(metafile) {
  const outputs = Object.keys(metafile.outputs).map((file) => path.basename(file));
  const app = outputs.find((file) => file.startsWith('app') && file.endsWith('.js'));
  const styles = outputs.find((file) => file.startsWith('styles') && file.endsWith('.css'));
  if (!app || !styles) throw new Error('esbuild did not produce app.js and styles.css');
  const template = await readFile(path.join(root, 'web', 'index.html'), 'utf8');
  let html = template.replace('/assets/APP', `${base}${app}`).replace('/assets/STYLES', `${base}${styles}`);
  if (isStatic) html = html.replace('href="/favicon.svg"', 'href="favicon.svg"');
  await writeFile(path.join(out, 'index.html'), html);
  await copyFile(path.join(root, 'web', 'static', 'favicon.svg'), path.join(out, 'favicon.svg'));
  if (isStatic) await writeFile(path.join(out, '.nojekyll'), '');
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
  define: { __STATIC__: isStatic ? 'true' : 'false' },
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

await rm(path.join(out, 'assets'), { recursive: true, force: true });
await mkdir(path.join(out, 'assets'), { recursive: true });
if (watch) {
  const ctx = await context(options);
  await ctx.watch();
  console.log('Watching web/src and web/styles. Reload the browser after each rebuild.');
} else {
  await build(options);
}
