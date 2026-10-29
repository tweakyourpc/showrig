# Showrig guided workflow proposal

Status: design proposal, not an implemented interface change. Based on the user's hands-on testing and inspection of the current source.

## The problem to solve

The user had to scroll long pages and open too many subsections. They reached Export with several unintentionally blank template scenes, pressed an action, and only discovered the error after scrolling to the page's top. Finding the offending scene then required going back several screens.

Source findings:
- The `step` / `next` handler in `showrig/static/app.js` saves the storyboard and advances without readiness validation.
- `showrig/studio.py:validate` rejects empty scenes only when called with `render=True`. It returns a generic error without a scene/field location.
- The browser's catch handler calls `notify`, which places that error in `#notice` above the page rather than beside the action.
- Templates create multiple scenes, while the Story panel edits only one selected scene. Blank scenes can look like inactive placeholders rather than unfinished parts of the film.
- Narration is edited for all scenes in a separate Sound step, adding another pass through the same scene sequence.

## Recommended structure

Use three phases: **Start → Build scenes → Review & export**.

Start collects title, template and frame format. The main editing workspace focuses on one scene at a time:

| Left | Center | Right |
|---|---|---|
| Numbered scene outline with names and readiness indicators | Selected scene's text, media and optional narration | Scene preview with a clear layout/render distinction |

Keep a bottom action bar visible: save status, current scene position, Previous scene, Next scene, Review & export. On small screens use an Edit/Preview switch instead of putting a large preview above every form. Long scene outlines may scroll inside their panel; avoid making the whole page a long stack of settings.

Global look and music belong in a compact Film settings panel. Scene text, shots, narration and captions belong with the scene they affect. Keep essentials visible; place genuinely advanced settings in a clearly labeled drawer. Setup & extras remains outside the normal authoring sequence.

## Guided scenes

- Give the outline meaningful template-role labels such as Opening, Demonstration and Next step without inventing the user's content.
- Distinguish proposed template slots from actual scenes. Add the next suggested scene explicitly, or let the user explicitly skip/remove an unused slot. Do not silently include empty placeholders in the export.
- Show states such as Not started, Needs attention and Ready. State which scene is selected and how many actual scenes are complete.
- Next scene checks the current scene's required content. Offer a useful explanation and a route to the field, or an explicit Skip/remove scene choice. Preserve free backward navigation and draft saving.
- Optional narration, pictures and music must not become mandatory. A text-only film remains valid. A scene needs supported visible content, consistent with the actual renderer's rules.

## Validation and error recovery

Use one readiness contract for navigation/preflight and the backend export gate so rules do not disagree. Draft structural validation remains permissive enough to save incomplete work.

Readiness issues should identify their scene ID, field, owning panel, explanation and suggested action. Collect all blockers instead of revealing only one after each export attempt.

- Validate the current phase/scene before forward navigation, including clicking a later phase directly.
- Show field-specific errors next to their controls, with focus and an accessible announcement.
- Keep an error summary next to the triggering action in the persistent footer. Do not rely on a banner above the viewport.
- Provide direct Fix buttons, for example: Scene 3, add text or media. Selecting Fix opens that scene, expands the relevant settings if needed, highlights and focuses the field, and preserves all existing input.
- Review & export shows a compact readiness checklist before starting expensive work. Disabled actions always have a nearby explanation and a direct way to fix the blocker.
- Native-tool, missing-media and voice readiness problems link to the appropriate setup/media control instead of sending the user through unrelated scenes.
- Unexpected rendering failures stay next to the export controls with recovery guidance and the render log. Successful output remains available.

## Visual design tool

[FigCraft](https://getartcraft.com/apps/figcraft) is ArtCraft's interface-design and prototyping application. Its official page documents offline operation, frames, auto layout, components/variants, styles, variables and clickable prototypes. Use it for the screen structure and a reusable component system, then implement and test the behavior in Showrig's browser code.

Prototype the incomplete-scene and error-recovery paths as carefully as the successful path. A polished static screen cannot establish whether validation and recovery are usable. Keep FigCraft a design tool, not a new runtime requirement for Showrig.

## Priority and acceptance checks

1. First fix late validation and offscreen errors.
2. Reorganize around the scene-first workspace and persistent actions.
3. Refine spacing, typography, hierarchy and consistent component states in the prototype and browser.

Acceptance scenarios:
- A first-time user can complete a short film without searching through closed subsections for required fields.
- An unfinished scene is identified before the user reaches an unexplained export failure.
- From Export, one Fix action reaches the exact offending scene/control; correcting it returns the user to a clear next action.
- All required scene issues are visible together; drafts remain saveable and optional features remain optional.
- Footer actions and their messages remain visible on a typical laptop viewport and a small mobile viewport.
- Reordering scenes does not break Fix targets; use stable IDs.
- Tests deliberately cover a blank middle scene, an unused ending, missing recordings, moved media and unavailable tools, as well as the happy path.
- Existing film data, local/offline operation, FilmCraft editability and MP4 export remain intact.
