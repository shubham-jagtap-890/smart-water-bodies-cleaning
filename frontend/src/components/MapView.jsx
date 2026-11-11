import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

/** OpenStreetMap + Leaflet (free, no API key). markers: [{lat,lng,color,label,radius}] */
export default function MapView({ markers = [], center, zoom = 12, height = 320, onPick, pin }) {
  const el = useRef(null), map = useRef(null), layer = useRef(null), pinLayer = useRef(null);

  useEffect(() => {
    map.current = L.map(el.current).setView(center || [17.1, 74.55], zoom);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19, attribution: "&copy; OpenStreetMap contributors",
    }).addTo(map.current);
    layer.current = L.layerGroup().addTo(map.current);
    pinLayer.current = L.layerGroup().addTo(map.current);
    if (onPick) map.current.on("click", (e) => onPick(e.latlng.lat, e.latlng.lng));
    return () => map.current.remove();
    // eslint-disable-next-line
  }, []);

  useEffect(() => {
    layer.current.clearLayers();
    markers.forEach((m) =>
      L.circleMarker([m.lat, m.lng], { radius: m.radius || 8, color: m.color || "#2563eb", fillOpacity: 0.7 })
        .bindPopup(m.label || "").addTo(layer.current));
    if (markers.length && !center) {
      map.current.fitBounds(markers.map((m) => [m.lat, m.lng]), { padding: [30, 30], maxZoom: 15 });
    }
  }, [markers, center]);

  useEffect(() => {
    pinLayer.current.clearLayers();
    if (pin) {
      L.circleMarker([pin.lat, pin.lng], { radius: 10, color: "#dc2626", fillOpacity: 0.9 }).addTo(pinLayer.current);
      map.current.setView([pin.lat, pin.lng], Math.max(map.current.getZoom(), 15));
    }
  }, [pin]);

  return <div ref={el} style={{ height, borderRadius: 12, zIndex: 0 }} />;
}
