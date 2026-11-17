from pathlib import Path
from PIL import Image, ImageDraw
from pypdf import PdfReader
import json
ROOT=Path(__file__).resolve().parents[1]
d=ROOT/'tmp/university'
groups=[('guide',sorted(d.glob('guide-*.png'))),('books1',sorted(d.glob('books-*.png'))[:6]),('books2',sorted(d.glob('books-*.png'))[6:])]
for name,files in groups:
    if not files: continue
    canvas=Image.new('RGB',(744,550*((len(files)+1)//2)),'#dddddd')
    for i,p in enumerate(files):
        im=Image.open(p);im.thumbnail((370,524))
        canvas.paste(im,((i%2)*372,(i//2)*550))
        ImageDraw.Draw(canvas).text(((i%2)*372+8,(i//2)*550+525),p.name,fill='black')
    canvas.save(d/(name+'_contact.png'))
for p in sorted((ROOT/'output/pdf').glob('ENU_*.pdf')):
    r=PdfReader(p)
    print(p.name,'pages',len(r.pages),'empty_pages',[i+1 for i,x in enumerate(r.pages) if not (x.extract_text() or '').strip()],'links',sum(len(x.get('/Annots',[])) for x in r.pages))
