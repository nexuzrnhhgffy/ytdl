from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from pytubefix import YouTube
from pytubefix.cli import on_progress
from moviepy.audio.io.AudioFileClip import AudioFileClip
import os

app = FastAPI(title="YouTube Downloader API")

BASE_YT_URL = "https://www.youtube.com/watch?v="

def get_full_url(video_id: str) -> str:
    return f"{BASE_YT_URL}{video_id}"

def estimate_compressed_size(original_size_mb, bitrate_factor=0.6):
    if not original_size_mb:
        return "?"
    compressed = original_size_mb * bitrate_factor
    return f"{round(compressed, 2)} MB (est.)"

def convert_to_mp3(temp_path, title, quality):
    output_dir = "downloads"
    os.makedirs(output_dir, exist_ok=True)
    mp3_path = os.path.join(output_dir, f"{title} ({quality}).mp3")
    clip = AudioFileClip(temp_path)
    bitrate = {"High": "320k", "Medium": "192k", "Low": "128k"}[quality]
    clip.write_audiofile(mp3_path, bitrate=bitrate)
    clip.close()
    os.remove(temp_path)
    return mp3_path

def get_download_options(video_id: str):
    url = get_full_url(video_id)
    yt = YouTube(url, on_progress_callback=on_progress)
    streams = yt.streams.order_by('resolution').desc()
    choices = []
    for s in streams:
        res = s.resolution or "Audio only"
        type_ = "video+audio" if s.is_progressive else (
            "video only" if s.includes_video_track else "audio only")
        ext = s.mime_type.split("/")[-1]
        size_mb = round(s.filesize / 1048576, 2) if s.filesize else None
        est_size = estimate_compressed_size(size_mb)
        choices.append({
            "label": f"{res} | {type_} | {ext} | {est_size}",
            "resolution": res,
            "type": type_,
            "extension": ext
        })
    choices.append({"label": "Convert to MP3 – High Quality (320kbps)", "type": "mp3_high"})
    choices.append({"label": "Convert to MP3 – Medium Quality (192kbps)", "type": "mp3_medium"})
    choices.append({"label": "Convert to MP3 – Low Quality (128kbps)", "type": "mp3_low"})
    return choices, yt.title


# ---------- Request Schemas ----------
class VideoRequest(BaseModel):
    video_id: str


class DownloadRequest(BaseModel):
    video_id: str
    choice: str


@app.post("/get_choices")
def api_get_choices(req: VideoRequest):
    try:
        choices, title = get_download_options(req.video_id)
        return {"title": title, "choices": choices}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/download")
def api_download(req: DownloadRequest):
    try:
        url = get_full_url(req.video_id)
        output_dir = "downloads"
        os.makedirs(output_dir, exist_ok=True)
        yt = YouTube(url, on_progress_callback=on_progress)

        # MP3 Download
        if "mp3" in req.choice.lower():
            stream = yt.streams.filter(only_audio=True).first()
            if not stream:
                raise HTTPException(status_code=400, detail="No audio stream available")

            temp_path = stream.download(output_path=output_dir, filename="temp.mp4")

            if "high" in req.choice.lower():
                mp3_path = convert_to_mp3(temp_path, yt.title, "High")
            elif "medium" in req.choice.lower():
                mp3_path = convert_to_mp3(temp_path, yt.title, "Medium")
            else:
                mp3_path = convert_to_mp3(temp_path, yt.title, "Low")

            return FileResponse(mp3_path, filename=os.path.basename(mp3_path))

        # MP4 Download
        parts = req.choice.split(" | ")
        res = parts[0]
        ext = parts[2]
        stream = yt.streams.filter(res=res, mime_type=f"video/{ext}").first() or \
                 yt.streams.filter(res=res).first()

        if not stream:
            raise HTTPException(status_code=400, detail="Selected quality not available")

        output_path = stream.download(output_path=output_dir)
        return FileResponse(output_path, filename=os.path.basename(output_path))

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/")
def home():
    return {"message": "YouTube Downloader API running! Use /get_choices and /download with POST JSON body."}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=7860)
