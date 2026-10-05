Empty ReCode database reconstruction

This recipe derives the initializer from the exact upstream commit in reconstruction.lock.json. It reproduces only a never-populated 28,672-byte database. It is not authority to discard a populated or changed database.

Run `npm ci --ignore-scripts --no-audit --no-fund` here, then `node rebuild-empty.cjs /absolute/disposable/output.db`. The locked sql.js distribution is the same WASM used by the installed ReCode 0.1.16. The script verifies its inputs and output digest before writing.

Upstream: https://github.com/aiyuekuang/ReCode/commit/d8400faf7778d2bb922c1b141ff7f86056367350 (MIT). sql.js: https://github.com/sql-js/sql.js (MIT).
