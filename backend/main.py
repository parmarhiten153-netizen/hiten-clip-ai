import os, uuid, tempfile, subprocess, zipfile, json, re
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from faster_whisper import WhisperModel

app=FastAPI(title="Hiten Clip AI API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
MODEL_SIZE=os.getenv("WHISPER_MODEL","small")
model=None
def get_model():
    global model
    if model is None:
        model=WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
    return model

def run(cmd):
    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    if p.returncode: raise RuntimeError(p.stderr[-1800:])
    return p.stdout

def transcribe(path, language):
    lang=None if language.lower() in ("auto","auto detect","") else language[:2].lower()
    segments,info=get_model().transcribe(path,language=lang, vad_filter=True, word_timestamps=True)
    rows=[]
    for s in segments:
        txt=s.text.strip()
        if txt: rows.append({"start":round(s.start,2),"end":round(s.end,2),"text":txt})
    return rows, info.language

def score_text(text):
    t=text.lower()
    keywords=["wow","amazing","incredible","unbelievable","never","best","secret","mistake"," जीत"," जीत","लेकिन","क्यों","कैसे","देखो","भाई","वाह","शानदार","important","crazy","insane","finally","actually","why","how"]
    score=sum(1.4 for w in keywords if w in t)
    score+=min(len(re.findall(r"\w+",t))/18,2)
    score+=0.8*sum(t.count(x) for x in ["!","?"])
    return score

def make_highlights(rows, total, length):
    if not rows: return []
    windows=[]
    step=max(10,int(length*0.55))
    starts=list(range(0,max(1,int(total-length)+1),step))
    if not starts: starts=[0]
    for st in starts:
        en=min(total,st+length)
        inside=[x for x in rows if x["end"]>st and x["start"]<en]
        if not inside: continue
        text=" ".join(x["text"] for x in inside)
        density=sum(min(x["end"],en)-max(x["start"],st) for x in inside)/max(1,en-st)
        score=score_text(text)+density*3
        windows.append({"start":round(st,2),"end":round(en,2),"score":round(score,2),"transcript":text})
    windows.sort(key=lambda x:x["score"],reverse=True)
    picked=[]
    for w in windows:
        if all(abs(w["start"]-p["start"])>length*.6 for p in picked):
            picked.append(w)
        if len(picked)>=5: break
    return sorted(picked,key=lambda x:x["start"])

def srt_time(sec):
    ms=int(sec*1000); h=ms//3600000; ms%=3600000; m=ms//60000; ms%=60000; s=ms//1000; ms%=1000
    return f"{h:02}:{m:02}:{s:02},{ms:03}"

@app.get("/")
def root(): return {"name":"Hiten Clip AI API","status":"online"}
@app.get("/health")
def health(): return {"status":"ok","model":MODEL_SIZE}
@app.post("/analyze")
async def analyze(video: UploadFile=File(...), duration:int=Form(30), language:str=Form("auto")):
    ext=Path(video.filename or "upload.mp4").suffix or ".mp4"
    path=f"/tmp/{uuid.uuid4()}{ext}"
    with open(path,"wb") as f: f.write(await video.read())
    try:
        probe=json.loads(run(["ffprobe","-v","quiet","-print_format","json","-show_format",path]))
        total=float(probe["format"]["duration"])
        rows,detected=transcribe(path,language)
        highlights=make_highlights(rows,total,duration)
        return {"duration":total,"language":detected,"segments":rows,"highlights":highlights}
    except Exception as e: raise HTTPException(500,str(e))
    finally:
        try: os.remove(path)
        except: pass

@app.post("/export")
async def export(video:UploadFile=File(...), start:float=Form(...), end:float=Form(...), language:str=Form("auto"), aspect:str=Form("9:16")):
    work=Path("/tmp")/str(uuid.uuid4()); work.mkdir()
    src=work/("input"+(Path(video.filename or "video.mp4").suffix or ".mp4"))
    out=work/"clip.mp4"
    src.write_bytes(await video.read())
    try:
        rows,_=transcribe(str(src),language)
        sub=work/"captions.srt"
        selected=[x for x in rows if x["end"]>start and x["start"]<end]
        with open(sub,"w",encoding="utf-8") as f:
            for i,x in enumerate(selected,1):
                a=max(0,x["start"]-start); b=max(a+.1,min(end-start,x["end"]-start))
                f.write(f"{i}\n{srt_time(a)} --> {srt_time(b)}\n{x['text']}\n\n")
        vf="scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920" if aspect=="9:16" else ("scale=1080:1080:force_original_aspect_ratio=increase,crop=1080:1080" if aspect=="1:1" else "scale=1920:-2")
        subpath=str(sub).replace("\\","/").replace(":","\\:")
        vf+=f",subtitles='{subpath}':force_style='FontName=Arial,FontSize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1,Alignment=2,MarginV=90'"
        run(["ffmpeg","-y","-ss",str(start),"-i",str(src),"-t",str(max(.2,end-start)),"-vf",vf,"-c:v","libx264","-preset","veryfast","-crf","23","-c:a","aac","-b:a","128k","-movflags","+faststart",str(out)])
        return FileResponse(str(out),media_type="video/mp4",filename="hiten-clip.mp4",background=None)
    except Exception as e: raise HTTPException(500,str(e))
