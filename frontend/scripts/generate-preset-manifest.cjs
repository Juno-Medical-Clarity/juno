#!/usr/bin/env node
/**
 * Scans ../../preset-data/ and generates public/preset-data/manifest.json
 * Also copies all preset-data files into public/preset-data/ for serving.
 *
 * Run automatically as part of `npm run build`.
 */

const fs = require('fs');
const path = require('path');

const PRESET_SRC = path.resolve(__dirname, '../../preset-data');
const PRESET_DEST = path.resolve(__dirname, '../public/preset-data');
const MANIFEST_PATH = path.join(PRESET_DEST, 'manifest.json');
const ALLOWED_EXTS = new Set(['.pdf', '.txt', '.docx']);

function ensureDir(dir) {
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
}

function copyFile(src, dest) {
  ensureDir(path.dirname(dest));
  fs.copyFileSync(src, dest);
}

function scanPresets() {
  if (!fs.existsSync(PRESET_SRC)) {
    console.log('[preset-manifest] No preset-data/ directory found — skipping.');
    ensureDir(PRESET_DEST);
    fs.writeFileSync(MANIFEST_PATH, JSON.stringify({ processes: [] }, null, 2));
    return;
  }

  const processes = [];

  const groups = fs.readdirSync(PRESET_SRC).filter(name => {
    const fullPath = path.join(PRESET_SRC, name);
    return fs.statSync(fullPath).isDirectory();
  });

  for (const group of groups) {
    const groupPath = path.join(PRESET_SRC, group);
    const processDirs = fs.readdirSync(groupPath).filter(name => {
      return fs.statSync(path.join(groupPath, name)).isDirectory();
    });

    for (const processName of processDirs) {
      const processPath = path.join(groupPath, processName);
      const allFiles = fs.readdirSync(processPath);
      const dataFiles = allFiles.filter(f => {
        const ext = path.extname(f).toLowerCase();
        return ALLOWED_EXTS.has(ext);
      });

      if (dataFiles.length === 0) continue;

      const fileEntries = [];
      for (const filename of dataFiles) {
        const srcFile = path.join(processPath, filename);
        // URL path relative to public root
        const urlPath = `preset-data/${group}/${processName}/${filename}`;
        const destFile = path.join(PRESET_DEST, group, processName, filename);
        copyFile(srcFile, destFile);
        fileEntries.push({ name: filename, url: `/${urlPath}` });
      }

      processes.push({
        group,
        name: processName,
        files: fileEntries,
      });
    }
  }

  ensureDir(PRESET_DEST);
  fs.writeFileSync(MANIFEST_PATH, JSON.stringify({ processes }, null, 2));
  console.log(`[preset-manifest] Generated manifest with ${processes.length} process(es).`);
}

scanPresets();
