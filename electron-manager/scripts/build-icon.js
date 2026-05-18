// Rasterizes assets/icon.svg into PNGs (multiple sizes) + a multi-res icon.ico
// for Windows, plus a 16x16 tray.png picked up by main.js:buildTrayIcon().
//
// Run with:  npm run build:icon
//
// Dev dependencies: sharp (SVG -> PNG), png-to-ico (PNGs -> ICO bundle).

const fs = require('fs');
const path = require('path');
const sharp = require('sharp');
const pngToIco = require('png-to-ico');

const ASSETS = path.resolve(__dirname, '..', 'assets');
const SVG_PATH = path.join(ASSETS, 'icon.svg');
const TRAY_SVG_PATH = path.join(ASSETS, 'icon-tray.svg');
const PNG_SIZES = [16, 24, 32, 48, 64, 128, 256, 512];
const ICO_SIZES = [16, 24, 32, 48, 64, 128, 256];
// Small sizes use the chip-less tray variant — the "AI" pill goes unreadable
// below ~48px and turns into noise. 48+ uses the full icon.svg.
const SMALL_SIZE_CUTOFF = 48;

async function main() {
  if (!fs.existsSync(SVG_PATH)) {
    console.error(`missing ${SVG_PATH}`);
    process.exit(1);
  }
  fs.mkdirSync(ASSETS, { recursive: true });
  const svg = fs.readFileSync(SVG_PATH);
  const traySvg = fs.existsSync(TRAY_SVG_PATH) ? fs.readFileSync(TRAY_SVG_PATH) : svg;

  for (const size of PNG_SIZES) {
    const out = path.join(ASSETS, `icon-${size}.png`);
    const source = size < SMALL_SIZE_CUTOFF ? traySvg : svg;
    await sharp(source, { density: 384 })
      .resize(size, size, { fit: 'contain', background: { r: 0, g: 0, b: 0, alpha: 0 } })
      .png({ compressionLevel: 9 })
      .toFile(out);
    console.log(`wrote ${path.relative(process.cwd(), out)}`);
  }

  const trayOut = path.join(ASSETS, 'tray.png');
  fs.copyFileSync(path.join(ASSETS, 'icon-16.png'), trayOut);
  console.log(`wrote ${path.relative(process.cwd(), trayOut)}`);

  const icoOut = path.join(ASSETS, 'icon.ico');
  const icoSources = ICO_SIZES.map((s) => path.join(ASSETS, `icon-${s}.png`));
  const icoBuf = await pngToIco(icoSources);
  fs.writeFileSync(icoOut, icoBuf);
  console.log(`wrote ${path.relative(process.cwd(), icoOut)} (${ICO_SIZES.join(', ')})`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
