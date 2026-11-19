import os, uuid, tempfile, subprocess, zipfile, json, re
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
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


# YouTube OAuth: configure GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET and PUBLIC_BASE_URL in Render.
YOUTUBE_SCOPES=["https://www.googleapis.com/auth/youtube.upload","https://www.googleapis.com/auth/youtube.readonly"]
oauth_states={}
youtube_credentials=None
youtube_channel=None
def youtube_flow(state=None):
    client_id=os.getenv("GOOGLE_CLIENT_ID"); client_secret=os.getenv("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret: raise HTTPException(503,"YouTube OAuth is not configured. Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in Render environment variables.")
    redirect_uri=os.getenv("PUBLIC_BASE_URL","https://hiten-clip-ai.onrender.com").rstrip("/")+"/auth/youtube/callback"
    cfg={"web":{"client_id":client_id,"client_secret":client_secret,"auth_uri":"https://accounts.google.com/o/oauth2/auth","token_uri":"https://oauth2.googleapis.com/token","redirect_uris":[redirect_uri]}}
    flow=Flow.from_client_config(cfg,scopes=YOUTUBE_SCOPES,state=state); flow.redirect_uri=redirect_uri
    return flow
@app.get("/auth/youtube")
def youtube_auth():
    import secrets
    state=secrets.token_urlsafe(24); oauth_states[state]=True
    flow=youtube_flow(state)
    url,_=flow.authorization_url(access_type="offline",include_granted_scopes="true",prompt="consent")
    return RedirectResponse(url)
@app.get("/auth/youtube/callback")
def youtube_callback(code:str,state:str):
    global youtube_credentials,youtube_channel
    if not oauth_states.pop(state,None): raise HTTPException(400,"Invalid or expired OAuth state. Connect again.")
    flow=youtube_flow(state); flow.fetch_token(code=code); youtube_credentials=flow.credentials
    yt=build("youtube","v3",credentials=youtube_credentials)
    data=yt.channels().list(part="snippet",mine=True).execute()
    items=data.get("items",[])
    youtube_channel=items[0]["snippet"]["title"] if items else "Connected channel"
    return {"connected":True,"channel":youtube_channel,"message":"YouTube channel connected. You can close this tab and return to Hiten Clip AI."}
@app.get("/youtube/status")
def youtube_status():
    return {"connected":youtube_credentials is not None,"channel":youtube_channel}
@app.post("/youtube/upload")
async def youtube_upload(video:UploadFile=File(...),title:str=Form(...),description:str=Form(""),tags:str=Form(""),privacy_status:str=Form("private")):
    if youtube_credentials is None: raise HTTPException(401,"Connect your YouTube channel first.")
    if privacy_status not in ("private","unlisted","public"): raise HTTPException(400,"Invalid privacy status.")
    ext=Path(video.filename or "clip.mp4").suffix or ".mp4"; path=f"/tmp/{uuid.uuid4()}{ext}"
    with open(path,"wb") as f: f.write(await video.read())
    try:
        yt=build("youtube","v3",credentials=youtube_credentials)
        body={"snippet":{"title":title[:100],"description":description[:5000],"tags":[x.strip() for x in tags.split(",") if x.strip()][:500],"categoryId":"22"},"status":{"privacyStatus":privacy_status,"selfDeclaredMadeForKids":False}}
        response=yt.videos().insert(part="snippet,status",body=body,media_body=MediaFileUpload(path,chunksize=-1,resumable=True)).execute()
        return {"videoId":response.get("id"),"privacyStatus":privacy_status}
    except Exception as e: raise HTTPException(500,str(e))
    finally:
        try: os.remove(path)
        except: pass

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
