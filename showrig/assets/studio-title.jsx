// The wizard's responsive title treatment; text is measured in the rendering engine.
var T = TITLE, W = T.width, H = T.height, S = Math.min(W, H) / 1080;
var comp = app.project.items.addComp("Title " + T.name, W, H, 1, T.secs, T.fps);
var lower = T.layout === "lower", terminal = T.design === "terminal";
// inset: where the text starts, as a share of the width, leaving room for an image beside it.
var margin = Math.min(W, H) * 0.09, x0 = T.inset ? W * T.inset : margin, maxWidth = W - x0 - margin;
var accent = [parseInt(T.color.slice(1, 3), 16) / 255, parseInt(T.color.slice(3, 5), 16) / 255, parseInt(T.color.slice(5, 7), 16) / 255];
var end = Math.max(0.9, T.secs - 0.45);
function tr(layer, name) { return layer.property("ADBE Transform Group").property(name); }
function animate(layer, x, y, delay) {
  var pos = tr(layer, "ADBE Position"), opacity = tr(layer, "ADBE Opacity");
  pos.setValueAtTime(delay, [x, y + 22 * S]);
  pos.setValueAtTime(delay + 0.55, [x, y]);
  opacity.setValueAtTime(delay, 0); opacity.setValueAtTime(delay + 0.4, 100);
  opacity.setValueAtTime(end, 100); opacity.setValueAtTime(T.secs, 0);
}
function makeText(value, size, bold, color) {
  var layer = comp.layers.addText(value || " ");
  var prop = layer.property("ADBE Text Properties").property("ADBE Text Document");
  var doc = prop.value;
  doc.font = terminal ? T.mono : (bold ? "DejaVuSans-Bold" : "DejaVuSans");
  doc.fontSize = size; doc.fillColor = color; doc.applyFill = true; doc.applyStroke = false;
  doc.justification = ParagraphJustification.LEFT_JUSTIFY; doc.tracking = bold ? -15 : 0;
  prop.setValue(doc);
  return layer;
}
function setText(layer, value, size) {
  var prop = layer.property("ADBE Text Properties").property("ADBE Text Document");
  var doc = prop.value; doc.text = value; doc.fontSize = size; prop.setValue(doc);
}
function wrap(layer, value, size) {
  var words = value.replace(/\s+/g, " ").trim().split(" "), lines = [], line = "";
  for (var i = 0; i < words.length; i++) {
    var candidate = line ? line + " " + words[i] : words[i];
    setText(layer, candidate, size);
    if (layer.sourceRectAtTime(0, false).width > maxWidth && line) { lines.push(line); line = words[i]; }
    else line = candidate;
  }
  if (line) lines.push(line);
  setText(layer, lines.join("\n"), size);
  return lines.length;
}
var size = (lower ? 66 : 94) * S;
var title = makeText(T.name, size, true, [0.97, 0.98, 0.99]);
var bodySize = (lower ? 34 : 40) * S;
var body = makeText(T.tagline, bodySize, false, [0.78, 0.83, 0.86]);
var titleLines, bodyLines;
for (var attempt = 0; attempt < 30; attempt++) {
  titleLines = wrap(title, T.name, size);
  bodyLines = wrap(body, T.tagline, bodySize);
  var titleBox = title.sourceRectAtTime(0, false), bodyBox = body.sourceRectAtTime(0, false);
  if (titleBox.width <= maxWidth + 1 && bodyBox.width <= maxWidth + 1 &&
      titleLines * size * 1.3 + bodyLines * bodySize * 1.5 < H * (lower ? .42 : .58)) break;
  size *= .92; bodySize *= .92;
}
var totalHeight = titleLines * size * 1.3 + (T.tagline ? bodyLines * bodySize * 1.5 + 28 * S : 0);
// place low: in the empty band under the intro's row of screens.
var y = lower ? H - totalHeight - H * .17 : T.place === "low" ? Math.min(H * .72 - totalHeight / 2, H * .9 - totalHeight)
  : (H - totalHeight) / 2;
var scrim = comp.layers.addSolid([0.015, 0.025, 0.035], "Readability", W, Math.round(lower ? totalHeight + H * .27 : H), 1, T.secs);
tr(scrim, "ADBE Position").setValue([W / 2, lower ? H - (totalHeight + H * .27) / 2 : H / 2]);
if (!lower) {
  // Centred titles often sit over a bright 3D wall: darken a feathered band behind the text, not the whole frame.
  var band = new Shape(), pad = 90 * S;
  band.vertices = [[-200, y - pad], [W + 200, y - pad], [W + 200, y + totalHeight + pad], [-200, y + totalHeight + pad]];
  band.closed = true;
  var mask = scrim.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");
  mask.property("ADBE Mask Shape").setValue(band);
  mask.property("ADBE Mask Feather").setValue([0, 140 * S]);
}
tr(scrim, "ADBE Opacity").setValueAtTime(0, 0);
tr(scrim, "ADBE Opacity").setValueAtTime(.35, lower ? 78 : 66);
tr(scrim, "ADBE Opacity").setValueAtTime(end, lower ? 78 : 66);
tr(scrim, "ADBE Opacity").setValueAtTime(T.secs, 0);
scrim.moveToEnd();
var rule = comp.layers.addSolid(accent, "Accent", Math.round(terminal ? maxWidth : 74 * S), Math.max(2, Math.round(4 * S)), 1, T.secs);
tr(rule, "ADBE Anchor Point").setValue([0, 0]);
animate(rule, x0, y - 28 * S, .05);
var titleRect = title.sourceRectAtTime(0, false);
tr(title, "ADBE Anchor Point").setValue([titleRect.left, titleRect.top]);
animate(title, x0, y, .12);
var bodyRect = body.sourceRectAtTime(0, false);
tr(body, "ADBE Anchor Point").setValue([bodyRect.left, bodyRect.top]);
animate(body, x0, y + titleLines * size * 1.3 + 28 * S, .28);
if (terminal && T.name) {
  var prop = title.property("ADBE Text Properties").property("ADBE Text Document"), full = prop.value.text;
  for (var k = 0; k <= full.length; k++) {
    var doc = prop.value; doc.text = full.slice(0, k); prop.setValueAtTime(.12 + k * Math.min(.045, 1.2 / full.length), doc);
  }
}
if (T.subtitle) {
  var sub = makeText(T.subtitle, 25 * S, false, accent);
  wrap(sub, T.subtitle, 25 * S);
  animate(sub, x0, H - H * .08, .4);
}
comp;
