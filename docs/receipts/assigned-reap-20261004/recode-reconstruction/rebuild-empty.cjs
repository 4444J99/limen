// Initializer derived from ReCode under its MIT license; see LICENSE.ReCode.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const hash = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
async function main() {
  const lock = JSON.parse(fs.readFileSync(path.join(__dirname, 'reconstruction.lock.json')));
  const sqlBytes = fs.readFileSync(path.join(__dirname, 'initializer.sql.json'));
  if (hash(sqlBytes) !== lock.initializer_sha256) throw Error('Initializer differs from locked source');
  const pkgRoot = path.join(__dirname, 'node_modules/sql.js');
  const pkg = JSON.parse(fs.readFileSync(path.join(pkgRoot, 'package.json')));
  if (pkg.version !== lock.sql_js_version) throw Error('sql.js version differs from lock');
  for (const [name, digest] of Object.entries(lock.distribution_inputs)) {
    if (hash(fs.readFileSync(path.join(pkgRoot, name))) !== digest) throw Error('Distribution bytes differ: '+name);
  }
  const SQL = await require(path.join(pkgRoot, 'dist/sql-wasm.js'))({locateFile: name => path.join(pkgRoot, 'dist', name)});
  const db = new SQL.Database();
  const statements = JSON.parse(sqlBytes);
  if (statements.length !== 8) throw Error('Pinned initializer denominator differs');
  for (let i=0; i<statements.length; i++) {
    try { db.run(statements[i]); } catch(e) { if(i<5 || !e.message.includes('duplicate column name')) throw e; }
  }
  const bytes = Buffer.from(db.export());
  const result = {
    source_commit: lock.source_commit,
    sql_js_version: pkg.version,
    sqlite_version: db.exec('SELECT sqlite_version()')[0].values[0][0],
    bytes: bytes.length,
    sha256: hash(bytes),
    integrity: db.exec('PRAGMA integrity_check')[0].values[0][0],
    changes_rows: db.exec('SELECT COUNT(*) FROM changes')[0].values[0][0],
    sequence_rows: db.exec('SELECT COUNT(*) FROM sqlite_sequence')[0].values[0][0]
  };
  db.close();
  if (result.sqlite_version !== lock.sqlite_version || result.sha256 !== lock.expected_empty_sha256 || result.integrity !== 'ok' || result.changes_rows || result.sequence_rows) throw Error('Reconstructed database differs from expected empty state');
  if (process.argv[2]) fs.writeFileSync(path.resolve(process.argv[2]), bytes, {flag:'wx',mode:0o600});
  console.log(JSON.stringify({...result, matched:true}));
}
main().catch(e => {console.error(e.message);process.exitCode=1;});
