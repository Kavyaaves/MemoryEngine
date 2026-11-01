// A soft round dot, drawn once on a canvas: makes points look like glowing specks instead of squares.
import * as THREE from "three";

let texture: THREE.CanvasTexture | null = null;

export function glowTexture(): THREE.CanvasTexture {
  if (texture) return texture;
  const size = 64;
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const context = canvas.getContext("2d")!;
  const gradient = context.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  gradient.addColorStop(0, "rgba(255,255,255,1)");
  gradient.addColorStop(0.25, "rgba(255,255,255,0.55)");
  gradient.addColorStop(1, "rgba(255,255,255,0)");
  context.fillStyle = gradient;
  context.fillRect(0, 0, size, size);
  texture = new THREE.CanvasTexture(canvas);
  return texture;
}
