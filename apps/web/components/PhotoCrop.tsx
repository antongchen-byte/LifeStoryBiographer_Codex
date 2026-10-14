"use client";
import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { request, type MediaAsset } from "../lib/api";
import { Button } from "./ui/button";

type Preview = { url: string; width: number; height: number };
export default function PhotoCrop({
  scope,
  container,
  photoId,
  filename,
  disabled,
  onSaved,
}: {
  scope: "media" | "interview" | "screenplay" | "cinema";
  container: string;
  photoId: string;
  filename: string;
  disabled?: boolean;
  onSaved?: (asset: MediaAsset) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null),
    canvas = useRef<HTMLCanvasElement>(null);
  const loaded = useRef<HTMLImageElement | null>(null);
  const cache = useQueryClient();
  const [removeText, setRemoveText] = useState(false);
  const [areas, setAreas] = useState<
    { x: number; y: number; width: number; height: number }[]
  >([]);
  const start = useRef<{ x: number; y: number } | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [x, setX] = useState(0.5),
    [y, setY] = useState(0.5),
    [zoom, setZoom] = useState(1);
  const [resolution, setResolution] = useState("original");
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [saved, setSaved] = useState<{
    asset: MediaAsset;
    download_url: string;
  } | null>(null);
  const base = `/photos/${scope}/${encodeURIComponent(container)}/${encodeURIComponent(photoId)}`;
  const scale = preview
    ? Math.floor(Math.min(preview.width / 16, preview.height / 9) / zoom)
    : 0;
  const cropWidth = scale * 16,
    cropHeight = scale * 9;
  const size =
    resolution === "original"
      ? `${cropWidth} × ${cropHeight}`
      : { "720p": "1280 × 720", "1080p": "1920 × 1080", "4k": "3840 × 2160" }[
          resolution
        ];
  useEffect(() => {
    if (!preview || !loaded.current || !canvas.current || scale < 1) return;
    const image = loaded.current,
      context = canvas.current.getContext("2d")!;
    const sx = image.naturalWidth / preview.width,
      sy = image.naturalHeight / preview.height;
    context.clearRect(0, 0, 640, canvas.current.height);
    if (removeText) {
      context.drawImage(image, 0, 0, 640, canvas.current.height);
      const pixels = context.getImageData(0, 0, 640, canvas.current.height);
      areas.forEach((a) => {
        const w = pixels.width,
          h = pixels.height;
        const left = Math.floor(a.x * w),
          top = Math.floor(a.y * h);
        const right = Math.min(w, Math.ceil((a.x + a.width) * w));
        const bottom = Math.min(h, Math.ceil((a.y + a.height) * h));
        const sum = [0, 0, 0];
        let count = 0;
        const sample = (x: number, y: number) => {
          const offset = (y * w + x) * 4;
          sum.forEach((_, c) => {
            sum[c] += pixels.data[offset + c];
          });
          count++;
        };
        for (let i = 0; i < 32; i++) {
          const x = Math.min(
            w - 1,
            left + Math.floor(((right - left) * (i + 0.5)) / 32),
          );
          const y = Math.min(
            h - 1,
            top + Math.floor(((bottom - top) * (i + 0.5)) / 32),
          );
          if (top > 0) sample(x, top - 1);
          if (bottom < h) sample(x, bottom);
          if (left > 0) sample(left - 1, y);
          if (right < w) sample(right, y);
        }
        if (count) {
          context.fillStyle = `rgb(${sum.map((v) => Math.round(v / count)).join(",")})`;
          context.fillRect(left, top, right - left, bottom - top);
        }
      });
      return;
    }
    context.drawImage(
      image,
      Math.round((preview.width - cropWidth) * x) * sx,
      Math.round((preview.height - cropHeight) * y) * sy,
      cropWidth * sx,
      cropHeight * sy,
      0,
      0,
      640,
      360,
    );
  }, [preview, x, y, zoom, cropWidth, cropHeight, scale, removeText, areas]);
  async function open(text = false) {
    setRemoveText(text);
    setAreas([]);
    dialog.current?.showModal();
    setError("");
    setSaved(null);
    setPreview(null);
    setBusy(true);
    setX(0.5);
    setY(0.5);
    setZoom(1);
    setResolution("original");
    try {
      const data = await request<Preview>(base + "/preview");
      const image = new Image();
      image.src = data.url;
      await image.decode();
      loaded.current = image;
      setPreview(data);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function save() {
    setBusy(true);
    setError("");
    try {
      const result = await request<{ asset: MediaAsset; download_url: string }>(
        base + "/crop",
        {
          method: "POST",
          body: JSON.stringify({
            x,
            y,
            zoom,
            resolution,
            crop_enabled: !removeText,
            redactions: areas,
          }),
        },
      );
      setSaved(result);
      onSaved?.(result.asset);
      await cache.invalidateQueries({ queryKey: ["media"] });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Button variant="outline" disabled={disabled} onClick={() => void open()}>
        Crop / resize to 16:9
      </Button>
      <Button
        variant="outline"
        disabled={disabled}
        onClick={() => void open(true)}
      >
        Remove sensitive text
      </Button>
      <dialog
        ref={dialog}
        className="modal photo-crop-modal"
        aria-label={
          removeText
            ? `Remove text from ${filename}`
            : `Crop ${filename} to 16:9`
        }
        onCancel={(e) => {
          if (busy) e.preventDefault();
        }}
      >
        <h2>
          {removeText
            ? `Remove text from ${filename}`
            : `Crop ${filename} to 16:9`}
        </h2>
        <p>
          The original stays unchanged. A separate edited photo is saved to the
          Media Library.
        </p>
        {busy && <p role="status">Preparing photo…</p>}
        {error && <p role="alert">{error}</p>}
        {preview && (
          <>
            <details>
              <summary>
                View original ({preview.width} × {preview.height})
              </summary>
              <img src={preview.url} alt={`Original ${filename}`} />
            </details>
            <canvas
              ref={canvas}
              width={640}
              height={
                removeText && preview
                  ? Math.round((640 * preview.height) / preview.width)
                  : 360
              }
              style={
                removeText
                  ? {
                      aspectRatio: `${preview.width} / ${preview.height}`,
                      touchAction: "none",
                      cursor: "crosshair",
                    }
                  : undefined
              }
              aria-label={
                removeText ? "Mark sensitive text areas" : "16:9 crop preview"
              }
              onPointerDown={(e) => {
                if (!removeText || busy) return;
                const r = e.currentTarget.getBoundingClientRect();
                start.current = {
                  x: (e.clientX - r.left) / r.width,
                  y: (e.clientY - r.top) / r.height,
                };
                e.currentTarget.setPointerCapture(e.pointerId);
              }}
              onPointerUp={(e) => {
                if (!start.current || busy) return;
                const r = e.currentTarget.getBoundingClientRect();
                const x = Math.max(
                  0,
                  Math.min(1, (e.clientX - r.left) / r.width),
                );
                const y = Math.max(
                  0,
                  Math.min(1, (e.clientY - r.top) / r.height),
                );
                const a = start.current;
                start.current = null;
                if (Math.abs(x - a.x) > 0.001 && Math.abs(y - a.y) > 0.001) {
                  setAreas((current) => [
                    ...current,
                    {
                      x: Math.min(x, a.x),
                      y: Math.min(y, a.y),
                      width: Math.abs(x - a.x),
                      height: Math.abs(y - a.y),
                    },
                  ]);
                  setSaved(null);
                }
              }}
              onPointerCancel={() => {
                start.current = null;
              }}
            />
            {removeText && (
              <>
                <p>
                  Drag rectangles over every text area to remove. Marked areas
                  are filled with the average color just outside each box. Check
                  the whole photo before saving. Text outside your selections
                  remains visible.
                </p>
                <Button
                  variant="outline"
                  disabled={busy || !areas.length}
                  onClick={() => {
                    setAreas((current) => current.slice(0, -1));
                    setSaved(null);
                  }}
                >
                  Undo last area
                </Button>
                <p>
                  {areas.length} areas marked. Original resolution is preserved.
                </p>
              </>
            )}
            {!removeText && (
              <>
                <label>
                  Zoom
                  <input
                    type="range"
                    min="1"
                    max="8"
                    step=".05"
                    value={zoom}
                    disabled={busy}
                    onChange={(e) => {
                      setZoom(+e.target.value);
                      setSaved(null);
                    }}
                  />
                </label>
                <label>
                  Horizontal position
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step=".01"
                    value={x}
                    disabled={busy}
                    onChange={(e) => {
                      setX(+e.target.value);
                      setSaved(null);
                    }}
                  />
                </label>
                <label>
                  Vertical position
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step=".01"
                    value={y}
                    disabled={busy}
                    onChange={(e) => {
                      setY(+e.target.value);
                      setSaved(null);
                    }}
                  />
                </label>
                <label>
                  Output size
                  <select
                    value={resolution}
                    disabled={busy}
                    onChange={(e) => {
                      setResolution(e.target.value);
                      setSaved(null);
                    }}
                  >
                    <option value="original">
                      Original crop resolution (no enlargement)
                    </option>
                    <option value="720p">1280 × 720</option>
                    <option value="1080p">1920 × 1080</option>
                    <option value="4k">3840 × 2160</option>
                  </select>
                </label>
                <p>Saved image: {size} pixels. The preview is scaled to fit.</p>
                {scale < 1 && (
                  <p role="alert">
                    Reduce zoom: at least 16 × 9 source pixels are required.
                  </p>
                )}
              </>
            )}
            <Button
              disabled={
                busy || (removeText ? !areas.length : scale < 1) || !!saved
              }
              onClick={() => void save()}
            >
              {removeText ? "Save text-removed copy" : "Save cropped copy"}
            </Button>
          </>
        )}
        {saved && (
          <div role="status">
            <p>
              Saved {saved.asset.original_filename} ({saved.asset.width} ×{" "}
              {saved.asset.height}).{" "}
              {scope !== "cinema" &&
                "Select this copy when attaching photo materials."}
            </p>
            <a className="button button-secondary" href={saved.download_url}>
              {removeText
                ? "Download text-removed photo"
                : "Download cropped photo"}
            </a>
          </div>
        )}
        <Button
          variant="outline"
          disabled={busy}
          onClick={() => dialog.current?.close()}
        >
          Close crop editor
        </Button>
      </dialog>
    </>
  );
}
