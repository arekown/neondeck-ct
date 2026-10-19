// Neondeck CT: meldet dem Dienst das aktive Fenster und die Fensterliste und setzt neue
// Fenster auf Wunsch an ihren Platz. Ereignisgesteuert (keine Abfrage im Takt).
// Laden/Entladen: Dienst ueber org.kde.KWin /Scripting (Skriptname "neondeck-ct").
var SERVICE = "io.github.arekown.NeondeckCT";
var OBJECT = "/Window";
var IFACE = "io.github.arekown.NeondeckCT.Window";
var LIST_DELAY_MS = 200;  // Aenderungen an der Liste sammeln (z. B. Titel, die oft wechseln)

function text(v) {
    return v ? String(v) : "";
}

function reportActive(w) {
    if (!w) return;
    callDBus(SERVICE, OBJECT, IFACE, "activated",
             text(w.resourceClass), text(w.desktopFileName), text(w.caption), Number(w.pid || 0));
}

// Nur echte Anwendungsfenster (keine Leisten, Menues, Tooltips, versteckten Helfer).
function listed(w) {
    return w && w.normalWindow && !w.skipTaskbar;
}

var gone = {};  // internalId entfernter Fenster bis zur naechsten Meldung

function reportWindows() {
    var out = [];
    var all = workspace.windowList();
    for (var i = 0; i < all.length; i++) {
        var w = all[i];
        // waehrend windowRemoved kann das Fenster noch in windowList() stehen
        if (!listed(w) || gone[String(w.internalId)]) continue;
        out.push({resourceClass: text(w.resourceClass), desktopFileName: text(w.desktopFileName),
                  caption: text(w.caption), pid: Number(w.pid || 0),
                  internalId: String(w.internalId)});
    }
    gone = {};
    callDBus(SERVICE, OBJECT, IFACE, "windowsChanged", JSON.stringify(out));
}

// hoechstens eine Meldung je LIST_DELAY_MS
var listTimer = new QTimer();
listTimer.singleShot = true;
listTimer.interval = LIST_DELAY_MS;
listTimer.timeout.connect(reportWindows);

function scheduleWindows() {
    if (!listTimer.active) listTimer.start();
}

function watch(w) {
    if (!w || !w.normalWindow) return;
    w.captionChanged.connect(function () {
        if (listed(w)) scheduleWindows();
    });
    w.desktopFileNameChanged.connect(function () {
        if (listed(w)) scheduleWindows();
    });
}

// --- Platzieren --------------------------------------------------------------------------
// Der Dienst sagt je neuem Fenster, wohin es soll: {"screen": Ausgang oder Lage, "place": ...}
// oder "" (nichts tun). Lagen: left/center/right/top/bottom nach den Bildschirm-Mitten.

function center(o) {
    var g = o.geometry;
    return {x: g.x + g.width / 2, y: g.y + g.height / 2};
}

// Bildschirm zu einer Angabe: Ausgangsname (Gross/klein egal), sonst Lage; null = unbekannt.
// Gleichstand: links/mitte/rechts nehmen den unteren (obere Monitore sind meist Zusatz),
// oben/unten den waagerecht mittigsten.
function findOutput(screens, want) {
    if (!want || !screens.length) return null;
    var low = String(want).toLowerCase();
    for (var i = 0; i < screens.length; i++) {
        if (String(screens[i].name).toLowerCase() === low) return screens[i];
    }
    var minX = Infinity, maxX = -Infinity;
    for (var j = 0; j < screens.length; j++) {
        var g = screens[j].geometry;
        minX = Math.min(minX, g.x);
        maxX = Math.max(maxX, g.x + g.width);
    }
    var midX = (minX + maxX) / 2;
    var score = {
        left: function (c) { return [c.x, -c.y]; },
        right: function (c) { return [-c.x, -c.y]; },
        center: function (c) { return [Math.abs(c.x - midX), -c.y]; },
        top: function (c) { return [c.y, Math.abs(c.x - midX)]; },
        bottom: function (c) { return [-c.y, Math.abs(c.x - midX)]; }
    }[low];
    if (!score) return null;
    var best = null, bestScore = null;
    for (var k = 0; k < screens.length; k++) {
        var s = score(center(screens[k]));
        if (best === null || s[0] < bestScore[0] - 0.5
                || (Math.abs(s[0] - bestScore[0]) <= 0.5 && s[1] < bestScore[1])) {
            best = screens[k];
            bestScore = s;
        }
    }
    return best;
}

// Zielrechteck in der Arbeitsflaeche ``a`` (ohne Leisten); "none": Groesse behalten, mittig.
function placeRect(a, place, current) {
    var hw = Math.round(a.width / 2), hh = Math.round(a.height / 2);
    var r = {
        maximize: [0, 0, a.width, a.height],
        left: [0, 0, hw, a.height], right: [hw, 0, a.width - hw, a.height],
        top: [0, 0, a.width, hh], bottom: [0, hh, a.width, a.height - hh],
        top_left: [0, 0, hw, hh], top_right: [hw, 0, a.width - hw, hh],
        bottom_left: [0, hh, hw, a.height - hh], bottom_right: [hw, hh, a.width - hw, a.height - hh]
    }[place];
    if (r) return {x: a.x + r[0], y: a.y + r[1], width: r[2], height: r[3]};
    var w = Math.min(current.width, a.width), h = Math.min(current.height, a.height);
    return {x: Math.round(a.x + (a.width - w) / 2), y: Math.round(a.y + (a.height - h) / 2),
            width: w, height: h};
}

function applyPlacement(w, reply) {
    if (!reply) return;
    var want;
    try {
        want = JSON.parse(String(reply));
    } catch (e) {
        return;
    }
    var output = findOutput(workspace.screens, want.screen) || w.output;
    var area = workspace.clientArea(KWin.MaximizeArea, output, workspace.currentDesktop);
    if (w.maximizable) w.setMaximize(false, false);
    w.frameGeometry = placeRect(area, want.place, w.frameGeometry);
    if (want.place === "maximize" && w.maximizable) w.setMaximize(true, true);
}

function askPlacement(w) {
    callDBus(SERVICE, OBJECT, IFACE, "placement", text(w.resourceClass),
             text(w.desktopFileName), Number(w.pid || 0),
             function (reply) { applyPlacement(w, reply); });
}

workspace.windowActivated.connect(reportActive);
workspace.windowAdded.connect(function (w) {
    watch(w);
    if (listed(w)) {
        scheduleWindows();
        askPlacement(w);
    }
});
workspace.windowRemoved.connect(function (w) {
    if (!listed(w)) return;
    gone[String(w.internalId)] = true;
    scheduleWindows();
});

var initial = workspace.windowList();
for (var i = 0; i < initial.length; i++) watch(initial[i]);
reportWindows();
reportActive(workspace.activeWindow);
