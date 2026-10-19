// Neondeck CT: Einmal-Skript zum Fokussieren (Dienst laedt es, laesst es laufen und
// entlaedt es sofort wieder). Fenster-ID und App setzt der Dienst als JSON-Text ein
// (Platzhalter __ID__ und __APP__).
// Fenster ueber internalId, sonst erstes Anwendungsfenster der App (desktopFileName/resourceClass).
(function () {
    var id = __ID__, app = __APP__, all = workspace.windowList(), hit = null;
    for (var i = 0; i < all.length; i++) {
        var w = all[i];
        if (String(w.internalId) === id) { hit = w; break; }
        if (!hit && w.normalWindow && (String(w.desktopFileName || "").toLowerCase() === app
                || String(w.resourceClass || "").toLowerCase() === app)) hit = w;
    }
    if (!hit) return;
    if (hit.minimized) hit.minimized = false;
    workspace.activeWindow = hit;
})();
