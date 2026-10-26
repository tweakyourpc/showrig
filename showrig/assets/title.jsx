// Showrig title card for EffectCraft. Expects TITLE = {name, tagline, subtitle, color, secs, layout,
// style, mono, width, height, fps} to be defined before this file. Renders over transparency.
//   layout: center | lower      style: rise | typewriter
var T = TITLE;
var W = T.width, H = T.height, FPS = T.fps;
var S = Math.min(W / 1920, H / 1080);          // scale everything from a 1080p design
var comp = app.project.items.addComp("Title " + T.name, W, H, 1, T.secs, FPS);
comp.bgColor = [0, 0, 0];

function hex(c) {
  return [parseInt(c.slice(1, 3), 16) / 255, parseInt(c.slice(3, 5), 16) / 255, parseInt(c.slice(5, 7), 16) / 255];
}
var accent = hex(T.color);
var centered = T.layout === "center";
var x0 = centered ? W / 2 : 150 * S;
var yTitle = centered ? H / 2 + 230 * S : H - 345 * S;

function tr(layer, name) { return layer.property("ADBE Transform Group").property(name); }
function ease(prop) {
  for (var k = 1; k <= prop.numKeys; k++) {
    prop.setInterpolationTypeAtKey(k, KeyframeInterpolationType.BEZIER, KeyframeInterpolationType.BEZIER);
    var e = [new KeyframeEase(0, 85)];
    if (prop.value instanceof Array) { e = []; for (var d = 0; d < prop.value.length; d++) e.push(new KeyframeEase(0, 85)); }
    prop.setTemporalEaseAtKey(k, e, e);
  }
}
function keys(prop, pairs) {
  for (var i = 0; i < pairs.length; i++) prop.setValueAtTime(pairs[i][0], pairs[i][1]);
  ease(prop);
}
function text(str, size, font, color, tracking, left) {
  var l = comp.layers.addText(str);
  var src = l.property("ADBE Text Properties").property("ADBE Text Document");
  var doc = src.value;
  doc.font = font; doc.fontSize = size * S; doc.fillColor = color; doc.applyFill = true; doc.applyStroke = false;
  doc.tracking = tracking || 0;
  doc.justification = centered && !left ? ParagraphJustification.CENTER_JUSTIFY : ParagraphJustification.LEFT_JUSTIFY;
  src.setValue(doc);
  return l;
}
// Type text on one character at a time, with a blinking cursor while it types.
function typeOn(layer, str, from, cps) {
  var src = layer.property("ADBE Text Properties").property("ADBE Text Document");
  var dt = 1 / cps;
  for (var i = 0; i <= str.length; i++) {
    var d = src.valueAtTime(0, false);
    d.text = str.slice(0, i) + "_";
    src.setValueAtTime(from + i * dt, d);
  }
  var end = from + str.length * dt;
  for (var b = 1; b <= 4; b++) {
    var d2 = src.valueAtTime(0, false);
    d2.text = str + (b % 2 ? "" : "_");
    src.setValueAtTime(end + b * 0.25, d2);
  }
  return end;
}
var outAt = T.secs - 0.7;
var typing = T.style === "typewriter";

// Dark scrim over the lower part of the frame so titles read over bright footage.
var scrim = comp.layers.addSolid([0, 0, 0], "Scrim", W, H, 1, T.secs);
var sm = scrim.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");
var shape = new Shape();
var top = centered ? H / 2 + 20 * S : H - 520 * S;
shape.vertices = [[-200, top], [W + 200, top], [W + 200, H + 300], [-200, H + 300]];
shape.closed = true;
sm.property("ADBE Mask Shape").setValue(shape);
sm.property("ADBE Mask Feather").setValue([0, 160 * S]);
keys(tr(scrim, "ADBE Opacity"), [[0, 0], [0.5, 62], [outAt, 62], [T.secs, 0]]);

// Accent bar wipes in, glowing: a rule beside lower thirds, a line under centred titles.
var bar = centered ? comp.layers.addSolid(accent, "Accent", Math.round(180 * S), Math.round(6 * S), 1, T.secs)
                   : comp.layers.addSolid(accent, "Accent", Math.round(12 * S), Math.round(120 * S), 1, T.secs);
if (centered) {
  tr(bar, "ADBE Position").setValue([W / 2, yTitle + 140 * S]);
  keys(tr(bar, "ADBE Scale"), [[0.5, [0, 100]], [1.3, [100, 100]], [outAt, [100, 100]], [T.secs, [0, 100]]]);
} else {
  tr(bar, "ADBE Anchor Point").setValue([6 * S, 120 * S]);
  tr(bar, "ADBE Position").setValue([x0 - 40 * S, yTitle + 30 * S]);
  keys(tr(bar, "ADBE Scale"), [[0.15, [100, 0]], [0.7, [100, 100]], [outAt, [100, 100]], [T.secs, [100, 0]]]);
}
bar.property("ADBE Effect Parade").addProperty("ADBE Glo2");

var size = centered ? (T.name.length > 14 ? 118 : 150) : 132;
var title, tagFrom = 0.7;
if (typing) {
  // Left-justified so the line grows to the right; centred layouts start from the measured left edge.
  title = text(T.name, size, T.mono || "JetBrainsMono-Bold", [1, 1, 1], 0, true);
  var wFull = title.sourceRectAtTime(0, false).width;
  var xLeft = centered ? W / 2 - wFull / 2 : x0;
  tr(title, "ADBE Position").setValue([xLeft, yTitle]);
  tagFrom = typeOn(title, T.name, 0.25, Math.max(12, T.name.length / 1.1)) + 0.15;
  keys(tr(title, "ADBE Opacity"), [[outAt, 100], [T.secs, 0]]);
} else {
  // Rises out of a blur. (Text-animator range selectors do not render in EffectCraft yet,
  // so the whole line animates rather than each character.)
  title = text(T.name, size, "Inter-Bold", [1, 1, 1], -10);
  var blur = title.property("ADBE Effect Parade").addProperty("ADBE Gaussian Blur 2");
  keys(blur.property(1), [[0.2, 28 * S], [1.0, 0]]);
  keys(tr(title, "ADBE Opacity"), [[0.2, 0], [0.8, 100], [outAt, 100], [T.secs, 0]]);
  keys(tr(title, "ADBE Position"), [[0.2, [x0, yTitle + 34 * S]], [1.1, [x0, yTitle]], [outAt, [x0, yTitle]],
                                    [T.secs, [x0, yTitle - 24 * S]]]);
  keys(tr(title, "ADBE Scale"), [[0.2, [104, 104]], [1.2, [100, 100]]]);
}

if (T.tagline) {
  var tag = text(T.tagline, centered ? 46 : 44, "Inter-Regular", [0.86, 0.9, 0.95], 20);
  var yTag = yTitle + (centered ? 90 : 76) * S;
  keys(tr(tag, "ADBE Position"), [[tagFrom, [x0 + (centered ? 0 : 40 * S), yTag]], [tagFrom + 0.8, [x0, yTag]],
                                  [outAt, [x0, yTag]], [T.secs, [x0, yTag - 18 * S]]]);
  keys(tr(tag, "ADBE Opacity"), [[tagFrom, 0], [tagFrom + 0.7, 100], [outAt, 100], [T.secs, 0]]);
}
if (T.subtitle) {
  var sub = text(T.subtitle, 30, "JetBrainsMono-Regular", accent, 40);
  tr(sub, "ADBE Position").setValue([x0, yTitle + ((centered ? 90 : 76) + 56) * S]);
  keys(tr(sub, "ADBE Opacity"), [[tagFrom + 0.4, 0], [tagFrom + 1.0, 100], [outAt, 100], [T.secs, 0]]);
}
comp;
