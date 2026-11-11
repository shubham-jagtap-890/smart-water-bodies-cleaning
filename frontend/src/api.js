import exifr from "exifr";


export const getToken = () => localStorage.getItem("token");

export async function api(path, { method = "GET", body } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (getToken()) headers.Authorization = "Bearer " + getToken();
  const res = await fetch("/api" + path, { method, headers, body: body ? JSON.stringify(body) : undefined });
  let data = {};
  try { data = await res.json(); } catch { /* empty body */ }
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

// Resize a photo in the browser (max 1024 px, JPEG) so uploads stay small and fast.
export async function fileToDataUrl(file, max = 1024) {
  let source = file;

  const isHeic =
    file.type === "image/heic" ||
    file.type === "image/heif" ||
    /\.(heic|heif)$/i.test(file.name);

  // Convert HEIC/HEIF to JPEG for browser compatibility
  if (isHeic) {
    try {
      const { default: heic2any } = await import("heic2any");
      const converted = await heic2any({
        blob: file,
        toType: "image/jpeg",
        quality: 0.9,
      });

      source = Array.isArray(converted) ? converted[0] : converted;
    } catch (error) {
      throw new Error("Could not convert HEIC photo. Please try another photo.");
    }
  }

  return new Promise((resolve, reject) => {
    const img = new Image();
    const objectUrl = URL.createObjectURL(source);

    img.onload = () => {
      URL.revokeObjectURL(objectUrl);

      try {
        const s = Math.min(1, max / Math.max(img.width, img.height));
        const c = document.createElement("canvas");

        c.width = Math.round(img.width * s);
        c.height = Math.round(img.height * s);

        c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);

        resolve(c.toDataURL("image/jpeg", 0.72));
      } catch {
        reject(new Error("Could not process the photo"));
      }
    };

    img.onerror = () => {
      URL.revokeObjectURL(objectUrl);
      reject(new Error("Could not read the photo"));
    };

    img.src = objectUrl;
  });
}

export function getLocation() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) return reject(new Error("Geolocation is not supported by this browser"));
    navigator.geolocation.getCurrentPosition(
      (p) => resolve({ lat: p.coords.latitude, lng: p.coords.longitude, accuracy: p.coords.accuracy }),
      () => reject(new Error("Location permission denied - please allow location access")),
      {
  enableHighAccuracy: true,
  timeout: 30000,
  maximumAge: 0
}
    );
  });
}

export const STATUS_LABEL = {
  ASSIGNED: "Awaiting inspection", ACTION_PLANNED: "Cleaning planned", COMPLETED: "Completed",
  NO_ACTION: "No action possible", REJECTED: "Rejected (fake)",
};
export const STATUS_COLOR = {
  ASSIGNED: "#d97706", ACTION_PLANNED: "#2563eb", COMPLETED: "#16a34a", NO_ACTION: "#6b7280", REJECTED: "#dc2626",
};
export const fmt = (iso) => (iso ? new Date(iso).toLocaleString() : "-");
export const fmtDate = (iso) => (iso ? new Date(iso).toLocaleDateString() : "-");

// ---- geotag helpers -------------------------------------------------------
export const NEAR_M = 200;   // device must be this close to the photo location (server enforces the real value)

export function distanceM(a, b) {
  const r = 6371000, rad = (x) => (x * Math.PI) / 180;
  const dLat = rad(b.lat - a.lat), dLng = rad(b.lng - a.lng);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLng / 2) ** 2;
  return 2 * r * Math.asin(Math.sqrt(h));
}

// GPS stored inside the photo itself (EXIF). Must be read BEFORE resizing - resizing removes EXIF.
export async function readGeotag(file) {
  try {
    const g = await exifr.gps(file);
    if (g && Number.isFinite(g.latitude) && Number.isFinite(g.longitude)) return { lat: g.latitude, lng: g.longitude };
  } catch { /* no EXIF */ }
  return null;
}

// Read the photo geotag + resize the photo + read the device location at upload time.
export async function preparePhoto(file) {
  const out = { image: null, photo: null, device: null, err: "" };
  try {
    out.photo = await readGeotag(file);
    out.image = await fileToDataUrl(file);
  } catch (e) { out.err = e.message; return out; }
  let deviceErr = "";
  try { out.device = await getLocation(); } catch (e) { deviceErr = e.message; }
  if (!out.photo) out.err = "This photo has no geotag. Turn on 'Location tag' in your camera app, take the photo again and upload that file.";
  else if (!out.device) out.err = deviceErr;
  return out;
}

export const geoPayload = (p) => ({
  image: p.image, photo_lat: p.photo?.lat, photo_lng: p.photo?.lng,
  device_lat: p.device?.lat, device_lng: p.device?.lng,
});
