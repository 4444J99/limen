#!/usr/bin/env python3
"""Step 3 of the restore: picks.json -> full-res originals -> restored board.

After you confirm originals in confirm.html and click "Export picks" (saves
picks.json), run this. It:
  1. reads picks.json  {tile_id: uuid | "none"}
  2. exports each chosen original from Photos at FULL resolution, downloading
     from iCloud if needed (uses osxphotos, which drives Photos.app)
  3. copies them into the app's assets/originals/
  4. writes boards/tony-2017.restored.json with faithful.img -> the original

Usage:
  ./clipvenv/bin/pip install osxphotos          # one-time
  ./clipvenv/bin/python download_fill.py picks.json \
      /path/to/apps/vision-board-studio

Note: iCloud download drives Photos.app via automation; macOS may prompt once
to allow it. Run it yourself if a background process can't get that grant.
"""
import json, os, sys, subprocess, shutil, glob

def main():
    picks_path = sys.argv[1] if len(sys.argv) > 1 else 'confirm/picks.json'
    app_dir = sys.argv[2] if len(sys.argv) > 2 else None
    picks = json.load(open(picks_path))
    chosen = {tid: u for tid, u in picks.items() if u and u != 'none'}
    print(f'{len(chosen)} tiles have a chosen original; {len(picks)-len(chosen)} marked none.')
    if not chosen:
        print('Nothing to download.'); return

    stage = os.path.abspath('originals_staged'); os.makedirs(stage, exist_ok=True)
    # export each uuid at full res (download-missing pulls from iCloud)
    got = {}
    for tid, uuid in chosen.items():
        dest = os.path.join(stage, tid); os.makedirs(dest, exist_ok=True)
        cmd = ['osxphotos', 'export', dest, '--uuid', uuid,
               '--download-missing', '--convert-to-jpeg', '--jpeg-quality', '0.95',
               '--original-name', '--skip-edited']
        print('→', tid, uuid[:8]);
        r = subprocess.run(cmd, capture_output=True, text=True)
        files = [f for f in glob.glob(os.path.join(dest, '*'))
                 if f.lower().endswith(('.jpg', '.jpeg', '.png', '.heic'))]
        if files:
            got[tid] = max(files, key=os.path.getsize)
        else:
            print('   ! no file exported —', (r.stderr or r.stdout)[:120])

    if not app_dir:
        print('\nExported to', stage, '— pass the app dir to also fill the board.'); return

    # copy into app assets + write restored board
    orig_dir = os.path.join(app_dir, 'assets', 'originals'); os.makedirs(orig_dir, exist_ok=True)
    board = json.load(open(os.path.join(app_dir, 'boards', 'tony-2017.json')))
    filled = 0
    for t in board['tiles']:
        src = got.get(t['id'])
        if not src: continue
        ext = os.path.splitext(src)[1].lower() or '.jpg'
        rel = f'assets/originals/{t["id"]}{ext}'
        shutil.copy(src, os.path.join(app_dir, rel))
        t['faithful']['img'] = rel
        t['faithful']['restored_from_photos'] = True
        filled += 1
    out = os.path.join(app_dir, 'boards', 'tony-2017.restored.json')
    json.dump(board, open(out, 'w'), indent=2)
    print(f'\nFilled {filled} tiles with full-res originals.\nWrote {out}')
    print('Point the app at the restored board (rename over tony-2017.json) to see it.')

if __name__ == '__main__':
    main()
