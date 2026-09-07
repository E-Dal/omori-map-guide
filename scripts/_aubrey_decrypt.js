#!/usr/bin/env node
// Decrypt an OMORI .AUBREY / .KEL / .HERO file.
// Usage: node _aubrey_decrypt.js <path> [output_path]
//   - reads encrypted file, writes decrypted JSON (or yaml for .HERO) to stdout
//   - if output_path given, writes there instead
//
// Matches OMORI's Encryption.decrypt (GTP_CoreUpdates.js):
//   AES-256-CTR with first 16 bytes = IV, key = Steam launch arg (32 ASCII chars)
const fs = require('fs');
const crypto = require('crypto');
const path = require('path');

// The key is the game's, not this project's — read at run time so a public
// repository is not also a way to unpack a commercial game. See scripts/_keys.py.
const STEAM_KEY = (() => {
  if (process.env.OMORI_AUBREY_KEY) return process.env.OMORI_AUBREY_KEY;
  const local = path.join(__dirname, 'omori_keys.json');
  if (fs.existsSync(local)) {
    try { return JSON.parse(fs.readFileSync(local, 'utf8')).aubrey; } catch (e) { /* fall through */ }
  }
  console.error('No OMORI AES key. Put it in scripts/omori_keys.json as ' +
                '{"aubrey": "<32 ASCII chars>"} or set OMORI_AUBREY_KEY.');
  process.exit(1);
})();

if (process.argv.length < 3) {
  console.error('Usage: node _aubrey_decrypt.js <path> [output_path]');
  process.exit(1);
}
const inPath = process.argv[2];
const outPath = process.argv[3];

const enc = fs.readFileSync(inPath);
const iv = enc.slice(0, 16);
const body = enc.slice(16);
const decipher = crypto.createDecipheriv('aes-256-ctr', STEAM_KEY, iv);
const plain = Buffer.concat([decipher.update(body), decipher.final()]);

if (outPath) {
  fs.writeFileSync(outPath, plain);
  console.error(`wrote ${plain.length} bytes → ${outPath}`);
} else {
  process.stdout.write(plain);
}
