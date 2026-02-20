#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<USAGE
Easy-clip: clip video dari URL YouTube/MP4 atau file lokal.

Usage:
  ./easy-clip.sh --input <youtube_or_mp4_or_local_file> --start HH:MM:SS --end HH:MM:SS [--outdir ./output]

Output:
  <outdir>/clip-horizontal.mp4
  <outdir>/clip-vertical-9x16.mp4
USAGE
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Error: command '$1' tidak ditemukan." >&2
    exit 1
  }
}

is_hhmmss() {
  [[ "$1" =~ ^[0-9]{2}:[0-9]{2}:[0-9]{2}$ ]]
}

hhmmss_to_seconds() {
  local value="$1"
  local hh mm ss
  IFS=':' read -r hh mm ss <<<"$value"
  if ((10#$mm > 59 || 10#$ss > 59)); then
    echo "-1"
    return
  fi
  echo $((10#$hh * 3600 + 10#$mm * 60 + 10#$ss))
}

is_youtube_url() {
  local url="$1"
  [[ "$url" =~ ^https?://(www\.)?(youtube\.com|youtu\.be)/ ]]
}

is_http_url() {
  local url="$1"
  [[ "$url" =~ ^https?:// ]]
}

download_source() {
  local input="$1"
  local workdir="$2"

  if [[ -f "$input" ]]; then
    cp "$input" "$workdir/source-input"
    echo "$workdir/source-input"
    return
  fi

  if is_youtube_url "$input"; then
    require_cmd yt-dlp
    yt-dlp --no-playlist -f "bv*+ba/b" -o "$workdir/source.%(ext)s" "$input" >/dev/null
    local found
    found=$(find "$workdir" -maxdepth 1 -type f -name 'source.*' | head -n 1)
    if [[ -z "$found" ]]; then
      echo "Error: gagal download video YouTube." >&2
      exit 1
    fi
    echo "$found"
    return
  fi

  if is_http_url "$input"; then
    require_cmd curl
    curl -L --fail "$input" -o "$workdir/source.mp4" >/dev/null 2>&1
    echo "$workdir/source.mp4"
    return
  fi

  echo "Error: input tidak valid. Gunakan URL YouTube/MP4 atau path file lokal." >&2
  exit 1
}

INPUT=""
START=""
END=""
OUTDIR="./output"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --input)
      INPUT="${2:-}"
      shift 2
      ;;
    --start)
      START="${2:-}"
      shift 2
      ;;
    --end)
      END="${2:-}"
      shift 2
      ;;
    --outdir)
      OUTDIR="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Argumen tidak dikenal: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ -z "$INPUT" || -z "$START" || -z "$END" ]]; then
  usage
  exit 1
fi

if ! is_hhmmss "$START" || ! is_hhmmss "$END"; then
  echo "Error: format waktu harus HH:MM:SS." >&2
  exit 1
fi

START_SEC=$(hhmmss_to_seconds "$START")
END_SEC=$(hhmmss_to_seconds "$END")
if ((START_SEC < 0 || END_SEC < 0)); then
  echo "Error: menit/detik harus berada di range 00-59." >&2
  exit 1
fi
if ((END_SEC <= START_SEC)); then
  echo "Error: end time harus lebih besar dari start time." >&2
  exit 1
fi

require_cmd ffmpeg

mkdir -p "$OUTDIR"
WORKDIR=$(mktemp -d)
trap 'rm -rf "$WORKDIR"' EXIT

SOURCE_FILE=$(download_source "$INPUT" "$WORKDIR")

ffmpeg -y -ss "$START" -to "$END" -i "$SOURCE_FILE" \
  -map 0:v:0 -map 0:a? -c:v libx264 -c:a aac -movflags +faststart \
  "$OUTDIR/clip-horizontal.mp4" >/dev/null 2>&1

ffmpeg -y -ss "$START" -to "$END" -i "$SOURCE_FILE" \
  -map 0:v:0 -map 0:a? \
  -vf "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920" \
  -c:v libx264 -c:a aac -movflags +faststart \
  "$OUTDIR/clip-vertical-9x16.mp4" >/dev/null 2>&1

echo "Selesai. Hasil clip:"
echo "- $OUTDIR/clip-horizontal.mp4"
echo "- $OUTDIR/clip-vertical-9x16.mp4"
