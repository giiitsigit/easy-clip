const fs = require('node:fs');
const fsp = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { pipeline } = require('node:stream/promises');
const { spawn } = require('node:child_process');
const ytdl = require('ytdl-core');
const ffmpegPath = require('ffmpeg-static');

const TIME_RE = /^(\d{2}):(\d{2}):(\d{2})$/;

function json(res, status, data) {
  res.statusCode = status;
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.end(JSON.stringify(data));
}

function parseBody(req) {
  return new Promise((resolve, reject) => {
    let raw = '';
    req.on('data', (chunk) => {
      raw += chunk;
      if (raw.length > 10 * 1024 * 1024) {
        reject(new Error('Payload too large'));
        req.destroy();
      }
    });
    req.on('end', () => {
      try {
        resolve(raw ? JSON.parse(raw) : {});
      } catch {
        reject(new Error('Invalid JSON body'));
      }
    });
    req.on('error', reject);
  });
}

function toSeconds(value) {
  const match = TIME_RE.exec(value);
  if (!match) return -1;
  const hh = Number(match[1]);
  const mm = Number(match[2]);
  const ss = Number(match[3]);
  if (mm > 59 || ss > 59) return -1;
  return hh * 3600 + mm * 60 + ss;
}

function parseSegments(timestamps) {
  const lines = String(timestamps || '')
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  if (!lines.length) {
    throw new Error('Timestamp wajib diisi minimal 1 baris');
  }

  return lines.map((line, i) => {
    const idx = i + 1;
    const parts = line.replace('-', ' ').split(/\s+/).filter(Boolean);
    if (parts.length !== 2) {
      throw new Error(`Format baris ${idx} salah. Gunakan: HH:MM:SS HH:MM:SS`);
    }
    const [start, end] = parts;
    const startSec = toSeconds(start);
    const endSec = toSeconds(end);
    if (startSec < 0 || endSec < 0) {
      throw new Error(`Format waktu baris ${idx} harus HH:MM:SS`);
    }
    if (endSec <= startSec) {
      throw new Error(`Baris ${idx}: end time harus lebih besar dari start time`);
    }
    return { start, end };
  });
}

function isYoutubeUrl(input) {
  try {
    const u = new URL(input);
    return ['youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be', 'www.youtu.be'].includes(u.hostname);
  } catch {
    return false;
  }
}

async function downloadSource(sourceUrl, workDir) {
  const sourcePath = path.join(workDir, 'source.mp4');

  if (isYoutubeUrl(sourceUrl)) {
    if (!ytdl.validateURL(sourceUrl)) {
      throw new Error('URL YouTube tidak valid');
    }
    await pipeline(ytdl(sourceUrl, { quality: 'highestvideo' }), fs.createWriteStream(sourcePath));
    return sourcePath;
  }

  const response = await fetch(sourceUrl);
  if (!response.ok || !response.body) {
    throw new Error('Gagal mengunduh source video');
  }

  const contentType = response.headers.get('content-type') || '';
  if (!contentType.includes('video') && !sourceUrl.toLowerCase().endsWith('.mp4')) {
    throw new Error('Source harus URL video yang valid');
  }

  await pipeline(response.body, fs.createWriteStream(sourcePath));
  return sourcePath;
}

function runFfmpeg(args) {
  return new Promise((resolve, reject) => {
    const child = spawn(ffmpegPath, args, { stdio: ['ignore', 'pipe', 'pipe'] });
    let stderr = '';
    child.stderr.on('data', (c) => {
      stderr += c.toString();
    });
    child.on('error', reject);
    child.on('close', (code) => {
      if (code !== 0) {
        reject(new Error(stderr.trim() || 'ffmpeg gagal memproses video'));
      } else {
        resolve();
      }
    });
  });
}

function toBase64Payload(filePath) {
  const b64 = fs.readFileSync(filePath).toString('base64');
  return { filename: path.basename(filePath), mime: 'video/mp4', base64: b64 };
}

module.exports = async (req, res) => {
  if (req.method === 'GET') {
    return json(res, 200, { name: 'Easy-clip API', ok: true });
  }

  if (req.method !== 'POST') {
    return json(res, 405, { error: 'Method not allowed' });
  }

  let tempDir;
  try {
    const body = await parseBody(req);
    const sourceUrl = String(body.sourceUrl || '').trim();
    const mode = ['horizontal', 'vertical', 'both'].includes(body.mode) ? body.mode : 'both';
    const segments = parseSegments(body.timestamps);

    if (!sourceUrl) {
      return json(res, 400, { error: 'Link video wajib diisi' });
    }

    tempDir = await fsp.mkdtemp(path.join(os.tmpdir(), 'easy-clip-'));
    const sourcePath = await downloadSource(sourceUrl, tempDir);

    const items = [];

    for (let i = 0; i < segments.length; i += 1) {
      const segment = segments[i];
      const segDir = path.join(tempDir, `segment-${String(i + 1).padStart(2, '0')}`);
      await fsp.mkdir(segDir, { recursive: true });

      const result = {
        label: `Segment ${i + 1}: ${segment.start} - ${segment.end}`,
        horizontal: null,
        vertical: null,
      };

      if (mode === 'horizontal' || mode === 'both') {
        const horizontalPath = path.join(segDir, 'clip-horizontal.mp4');
        await runFfmpeg([
          '-y', '-ss', segment.start, '-to', segment.end, '-i', sourcePath,
          '-map', '0:v:0', '-map', '0:a?',
          '-c:v', 'libx264', '-c:a', 'aac', '-movflags', '+faststart',
          horizontalPath,
        ]);
        result.horizontal = toBase64Payload(horizontalPath);
      }

      if (mode === 'vertical' || mode === 'both') {
        const verticalPath = path.join(segDir, 'clip-vertical-9x16.mp4');
        await runFfmpeg([
          '-y', '-ss', segment.start, '-to', segment.end, '-i', sourcePath,
          '-map', '0:v:0', '-map', '0:a?',
          '-vf', 'scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920',
          '-c:v', 'libx264', '-c:a', 'aac', '-movflags', '+faststart',
          verticalPath,
        ]);
        result.vertical = toBase64Payload(verticalPath);
      }

      items.push(result);
    }

    return json(res, 200, {
      success: true,
      mode,
      count: items.length,
      items,
    });
  } catch (error) {
    return json(res, 400, { error: error.message || 'Terjadi kesalahan' });
  } finally {
    if (tempDir) {
      await fsp.rm(tempDir, { recursive: true, force: true });
    }
  }
};
