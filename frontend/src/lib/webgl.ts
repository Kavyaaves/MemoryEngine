// Can this browser render the 3D Life explorer? LifePage falls back to the list view when it can't.

let cachedResult: boolean | null = null;

export function isWebGLAvailable(): boolean {
  // Checked once per page load: the answer can't change while the app is open.
  if (cachedResult === null) cachedResult = detectWebGL();
  return cachedResult;
}

function detectWebGL(): boolean {
  try {
    const canvas = document.createElement("canvas");
    const gl = canvas.getContext("webgl2") ?? canvas.getContext("webgl");
    // Browsers allow only a handful of live WebGL contexts, so release the test context right away.
    gl?.getExtension("WEBGL_lose_context")?.loseContext();
    return gl !== null;
  } catch {
    return false;
  }
}
