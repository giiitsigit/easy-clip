# Easy-clip

Easy-clip punya **Web UI** + **CLI**.

## Fitur Web terbaru
- Input source video dari URL YouTube atau URL MP4.
- Input **multiple timestamp** (satu baris = satu clip).
- Opsi output via tombol:
  - **Generate Horizontal**
  - **Generate Vertical 9:16**
  - **Generate Both**
- Tiap hasil clip bisa preview langsung di browser + download.

Format timestamp per baris:
- `HH:MM:SS HH:MM:SS`
- atau `HH:MM:SS-HH:MM:SS`

## Dependency sistem
Pastikan command ini tersedia:
- `ffmpeg`
- `yt-dlp` (untuk YouTube)
- `curl` (untuk direct MP4 URL)
- `python3`

## Jalankan Web
```bash
python3 app.py
```
Buka `http://localhost:8080`.

Hasil clip akan disimpan ke folder `web_outputs/<job_id>/segment-xx/`.

## CLI (opsional)
```bash
./easy-clip.sh --input "https://www.youtube.com/watch?v=..." --start 00:00:10 --end 00:00:35 --outdir ./hasil
```
