from flask import Flask, request, jsonify, send_file
from pytubefix import YouTube
from pytubefix.cli import on_progress
from moviepy.audio.io.AudioFileClip import AudioFileClip
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

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
    
    # Sanitize filename
    safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()
    mp3_path = os.path.join(output_dir, f"{safe_title} ({quality}).mp3")
    
    clip = AudioFileClip(temp_path)
    bitrate = {"High": "320k", "Medium": "192k", "Low": "128k"}[quality]
    clip.write_audiofile(mp3_path, bitrate=bitrate, logger=None)
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
        type_ = "video+audio" if s.is_progressive else ("video only" if s.includes_video_track else "audio only")
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

@app.route("/get_choices")
def api_get_choices():
    video_id = request.args.get("video_id")
    if not video_id:
        return jsonify({"error": "video_id query parameter is required"}), 400
    
    try:
        logger.info(f"Getting choices for video: {video_id}")
        choices, title = get_download_options(video_id)
        return jsonify({"title": title, "choices": choices})
    except Exception as e:
        logger.error(f"Error getting choices: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/download")
def api_download():
    video_id = request.args.get("video_id")
    choice = request.args.get("choice")
    
    if not video_id or not choice:
        return jsonify({"error": "video_id and choice query parameters are required"}), 400
    
    try:
        logger.info(f"Downloading: {video_id} with choice: {choice}")
        url = get_full_url(video_id)
        output_dir = "downloads"
        os.makedirs(output_dir, exist_ok=True)
        yt = YouTube(url, on_progress_callback=on_progress)

        # MP3 conversion
        if "mp3" in choice.lower():
            stream = yt.streams.filter(only_audio=True).first()
            if not stream:
                return jsonify({"error": "No audio stream available"}), 400
            
            temp_path = stream.download(output_path=output_dir, filename="temp.mp4")
            
            if "high" in choice.lower():
                mp3_path = convert_to_mp3(temp_path, yt.title, "High")
            elif "medium" in choice.lower():
                mp3_path = convert_to_mp3(temp_path, yt.title, "Medium")
            else:
                mp3_path = convert_to_mp3(temp_path, yt.title, "Low")
            
            return send_file(mp3_path, as_attachment=True)

        # MP4 download
        res = choice.split(" | ")[0]
        ext = choice.split(" | ")[2]
        stream = yt.streams.filter(res=res, mime_type=f"video/{ext}").first()
        
        if not stream:
            stream = yt.streams.filter(res=res).first()
        if not stream:
            return jsonify({"error": "Selected quality not available"}), 400
        
        output_path = stream.download(output_path=output_dir)
        return send_file(output_path, as_attachment=True)

    except Exception as e:
        logger.error(f"Error during download: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/")
def home():
    return jsonify({
        "message": "YouTube Downloader API running!",
        "endpoints": {
            "/get_choices": "GET with ?video_id=VIDEO_ID",
            "/download": "GET with ?video_id=VIDEO_ID&choice=CHOICE_LABEL"
        }
    })

@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200
