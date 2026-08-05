import sqlite3,glob,os,json,sys,time
import numpy as np, torch, open_clip
from PIL import Image
Image.MAX_IMAGE_PIXELS=None

BASE=os.path.expanduser('~/Pictures/Photos Library.photoslibrary')
DERIV=BASE+'/resources/derivatives'; DB=BASE+'/database/Photos.sqlite'
dev='mps' if torch.backends.mps.is_available() else 'cpu'
CACHE='clip_cache.npz'

# 1) uuid -> best derivative, for all image assets
c=sqlite3.connect('file:%s?mode=ro'%DB, uri=True)
imgs=set(r[0] for r in c.execute('SELECT ZUUID FROM ZASSET WHERE ZKIND=0'))
print('image assets:',len(imgs),file=sys.stderr)
best={}
for root,_,files in os.walk(DERIV):
    for f in files:
        if not f.lower().endswith(('.jpeg','.jpg')): continue
        u=f.split('_')[0]
        if u not in imgs: continue
        p=os.path.join(root,f); sz=os.path.getsize(p)
        if u not in best or sz>best[u][1]: best[u]=(p,sz)
uuids=list(best.keys())
print('with derivative:',len(uuids),file=sys.stderr)

model,_,preprocess=open_clip.create_model_and_transforms('ViT-B-32',pretrained='laion2b_s34b_b79k')
model=model.to(dev).eval()

def embed_paths(paths,bs=64):
    outs=[]
    for i in range(0,len(paths),bs):
        batch=[]
        for p in paths[i:i+bs]:
            try: batch.append(preprocess(Image.open(p).convert('RGB')))
            except Exception: batch.append(torch.zeros(3,224,224))
        x=torch.stack(batch).to(dev)
        with torch.no_grad():
            f=model.encode_image(x); f=f/f.norm(dim=-1,keepdim=True)
        outs.append(f.cpu().numpy().astype('float32'))
        if i%1280==0: print('embed %d/%d'%(i,len(paths)),file=sys.stderr)
    return np.concatenate(outs)

if os.path.exists(CACHE):
    z=np.load(CACHE,allow_pickle=True); uuids=list(z['uuids']); E=z['E']
    print('loaded cache',E.shape,file=sys.stderr)
else:
    t0=time.time(); E=embed_paths([best[u][0] for u in uuids])
    np.savez(CACHE,uuids=np.array(uuids),E=E); print('embedded in %.0fs'%(time.time()-t0),file=sys.stderr)

# queries
tiles=sorted(glob.glob('tiles_out/*.png'))
Q=embed_paths(tiles)
os.makedirs('cmatches',exist_ok=True); out={}
for qi,t in enumerate(tiles):
    name=os.path.splitext(os.path.basename(t))[0]
    sims=E@Q[qi]; idx=np.argsort(-sims)[:8]
    out[name]=[{'uuid':uuids[j],'score':float(sims[j]),'deriv':best[uuids[j]][0]} for j in idx]
    cells=[Image.open(t).convert('RGB').resize((130,130))]
    for j in idx:
        try: cells.append(Image.open(best[uuids[j]][0]).convert('RGB').resize((130,130)))
        except: cells.append(Image.new('RGB',(130,130),(50,50,50)))
    sh=Image.new('RGB',(130*len(cells),140),(15,15,15))
    for k,cc in enumerate(cells): sh.paste(cc,(k*130,5))
    sh.save('cmatches/%s.png'%name)
json.dump(out,open('cmatches/_matches.json','w'),indent=2)
print('DONE',file=sys.stderr)
