// Showrig rolling credits for EffectCraft. Expects CREDITS = {title, lines, color, font, secs, width,
// height, fps} defined before this file. A line is [role, name], ["", name] for a centred name, or
// [heading] to start a section. font (optional) replaces Inter. Renders over transparency.
var C = CREDITS;
var W = C.width, H = C.height;
var S = Math.min(W / 1920, H / 1080);
var comp = app.project.items.addComp("Credits", W, H, 1, C.secs, C.fps);
function hex(c) {
  return [parseInt(c.slice(1, 3), 16) / 255, parseInt(c.slice(3, 5), 16) / 255, parseInt(c.slice(5, 7), 16) / 255];
}
function tr(layer, name) { return layer.property("ADBE Transform Group").property(name); }
function text(str, size, font, color, tracking, just) {
  var l = comp.layers.addText(str);
  var src = l.property("ADBE Text Properties").property("ADBE Text Document");
  var doc = src.value;
  doc.font = font; doc.fontSize = size * S; doc.fillColor = color; doc.applyFill = true; doc.applyStroke = false;
  doc.tracking = tracking || 0; doc.justification = just;
  src.setValue(doc);
  return l;
}
// One null carries every line, so the roll is a single linear move.
var roll = comp.layers.addNull(C.secs);
var gap = 92 * S, y = 0;
var bold = C.font || "Inter-Bold", regular = C.font || "Inter-Regular";
var head = text(C.title, 64, bold, [1, 1, 1], -5, ParagraphJustification.CENTER_JUSTIFY);
head.parent = roll; tr(head, "ADBE Position").setValue([0, y]);
y += gap * 1.6;
for (var i = 0; i < C.lines.length; i++) {
  var line = C.lines[i];
  if (line.length === 1) {
    if (i) y += gap * .6;
    var section = text(line[0].toUpperCase(), 28, bold, hex(C.color), 160, ParagraphJustification.CENTER_JUSTIFY);
    section.parent = roll; tr(section, "ADBE Position").setValue([0, y]);
    y += gap * .95;
    continue;
  }
  if (!line[0]) {
    var name = text(line[1], 36, bold, [1, 1, 1], 0, ParagraphJustification.CENTER_JUSTIFY);
    name.parent = roll; tr(name, "ADBE Position").setValue([0, y]);
    y += gap * .8;
    continue;
  }
  var role = text(line[0], 30, regular, hex(C.color), 30, ParagraphJustification.RIGHT_JUSTIFY);
  role.parent = roll; tr(role, "ADBE Position").setValue([-28 * S, y]);
  var who = text(line[1], 40, bold, [1, 1, 1], 0, ParagraphJustification.LEFT_JUSTIFY);
  who.parent = roll; tr(who, "ADBE Position").setValue([28 * S, y]);
  y += gap;
}
var travel = H + y + 120 * S;
var pos = tr(roll, "ADBE Position");
pos.setValueAtTime(0, [W / 2, H + 80 * S]);
pos.setValueAtTime(C.secs, [W / 2, H + 80 * S - travel]);
comp;
