var map = L.map('map').setView([12.9716, 77.5946], 13);

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png')
.addTo(map);

fetch('/api/potholes')
.then(res => res.json())
.then(data => {
  data.forEach(p => {
    let color =
      p.severity === "High" ? "red" :
      p.severity === "Medium" ? "orange" : "green";

    L.circleMarker([p.lat, p.lon], {
      radius: 8,
      color: color
    }).addTo(map)
    .bindPopup("Severity: " + p.severity);
  });
});