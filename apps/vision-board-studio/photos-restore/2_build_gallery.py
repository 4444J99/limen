import numpy as np, torch, open_clip, os, json, glob, sqlite3, shutil
from PIL import Image
z=np.load('clip_cache.npz',allow_pickle=True); uuids=list(z['uuids']); E=z['E']
dev='mps' if torch.backends.mps.is_available() else 'cpu'
model,_,preprocess=open_clip.create_model_and_transforms('ViT-B-32',pretrained='laion2b_s34b_b79k')
model=model.to(dev).eval(); tok=open_clip.get_tokenizer('ViT-B-32')
BASE=os.path.expanduser('~/Pictures/Photos Library.photoslibrary'); DERIV=BASE+'/resources/derivatives'
uset=set(uuids); best={}
for root,_,files in os.walk(DERIV):
    for f in files:
        if not f.lower().endswith(('.jpeg','.jpg')): continue
        u=f.split('_')[0]
        if u not in uset: continue
        p=os.path.join(root,f); sz=os.path.getsize(p)
        if u not in best or sz>best[u][1]: best[u]=(p,sz)
board=json.load(open('/Users/4jp/Workspace/limen/.claude/worktrees/feat-vision-board-studio/apps/vision-board-studio/boards/tony-2017.json'))
tiles=board['tiles']
# image embeddings of salvage crops
def embed_imgs(paths):
    xs=[preprocess(Image.open(p).convert('RGB')) for p in paths]
    with torch.no_grad():
        f=model.encode_image(torch.stack(xs).to(dev)); f=f/f.norm(dim=-1,keepdim=True)
    return f.cpu().numpy()
salv=[t['salvage'].split('/')[-1] for t in tiles]
salv=['tiles_out/'+os.path.splitext(s)[0]+'.png' for s in [t['id'] for t in tiles]]
QI=embed_imgs(salv)
texts=[f"{t['desc']}. {t['theme']}." for t in tiles]
with torch.no_grad():
    T=model.encode_text(tok(texts).to(dev)); T=(T/T.norm(dim=-1,keepdim=True)).cpu().numpy()
os.makedirs('confirm/thumbs',exist_ok=True)
cand={}
seen_copy=set()
for i,t in enumerate(tiles):
    s=0.8*(E@T[i])+0.2*(E@QI[i])
    idx=np.argsort(-s)[:15]
    lst=[]
    for j in idx:
        u=uuids[j]
        dst='confirm/thumbs/%s.jpg'%u
        if u not in seen_copy:
            try:
                im=Image.open(best[u][0]).convert('RGB'); im.thumbnail((240,240)); im.save(dst,quality=82)
                seen_copy.add(u)
            except: pass
        lst.append({'uuid':u,'score':float(s[j])})
    # copy salvage crop for display
    shutil.copy(salv[i],'confirm/thumbs/_q_%s.jpg'%t['id'] if False else 'confirm/thumbs/_q_%s.png'%t['id'])
    cand[t['id']]={'title':t['title'],'desc':t['desc'],'salvage':'thumbs/_q_%s.png'%t['id'],'cands':lst}
json.dump(cand,open('confirm/candidates.json','w'),indent=2)
print('tiles',len(tiles),'thumbs',len(seen_copy))
