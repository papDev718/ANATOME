---
name: anatomy-focus-zoom
description: Implement or adapt the click-triggered cinematic camera zoom and peripheral blur for a selectable muscle or anatomical structure in the ANATOME 3D viewer. Use when changing the anatomy model or its selection/focus interaction; do not use for unrelated app UI or report changes.
---

# Anatomy Focus Zoom

Preserve this interaction when the ANATOME model is replaced. The zoom belongs to the selected anatomy—not to a particular GLB filename or old mesh index—so reconnect it to the replacement model's raycast hit and current mesh/group structure.

## Interaction contract

- Clicking a selectable muscle selects it and starts a smooth dolly toward its anatomical center. Keep a narrow margin around the muscle so it dominates the viewport while nearby structures remain recognizable.
- Keep the rest of the body in frame as context, but softly dim it and blur the area outside the selected structure. The selected muscle remains crisp and visually distinct.
- Show the selected structure's detail panel without shrinking the 3D stage. Keep its scroll content and existing questionnaire/report flows intact.
- When the selection is cleared, restore the full-body framing, normal material states, and unblurred view. Selecting another structure retargets the animation cleanly.
- If detail sections already drive contextual camera views, preserve them: small angle/zoom changes should follow the same selected structure rather than restart from the full-body pose.

## Implementation guidance

1. Inspect the replacement GLB's named nodes and hierarchy. Connect raycast hits to a semantic structure record (mesh/group, readable name, and bounds); never rely on fragile child-array indices. If a hit is a child mesh, resolve it to its owning selectable structure.
2. On selection, calculate a world-space `Box3` and center for the selected structure. Derive camera distance from the bounding-box width, height, camera vertical FOV, and viewport aspect ratio so the complete target fits. Use a close framing margin (roughly `1.15–1.32 × fit distance`, tuned against the actual model scale); avoid a fixed distance that only works for the old GLB.
3. Preserve the user's current viewing side when possible. Aim from the current camera direction, adjusted only enough to see the selected structure clearly, and tween both `camera.position` and orbit/control target to the selected center. Use a restrained cinematic ease (for example GSAP `expo.out`, around `0.8–1.0 s`), kill or overwrite prior camera tweens before starting a new one, and update controls during motion. Honor `prefers-reduced-motion` by applying the end pose immediately.
4. Visually isolate selection through existing material state handling: highlight the selected structure and reduce the contrast/opacity of other structures without making surrounding anatomy disappear. Preserve original material values so deselection and repeated selections restore correctly.
5. Keep peripheral context softly blurred. A lightweight DOM overlay above the WebGL canvas can use `backdrop-filter: blur(...)` with a radial CSS mask centered on the selected structure; project the selected bounds/center into screen space and update the mask as the camera moves. Keep the center clear, blur/tint only the outside region, and disable pointer events on the overlay. This is a practical browser depth-of-field illusion, not true optical DOF.
6. Recompute the camera projection and projected blur mask after resizing, panel/layout changes, scroll-driven camera nudges, and orbit changes. Ensure pointer picking still works through non-interactive overlays, and avoid treating camera-drag gestures as clicks.
7. Test at least: full-body initial framing, selection of small and large muscles, rapid selection changes, clear/reset, resize, mobile layout, and reduced-motion mode. Confirm the selected anatomy stays crisp and nearly fills the view while adjacent anatomy remains perceptible.

## ANATOME v1 reference

The current v1 implementation uses `front_end/src/components/BodyPartsCanvas.jsx` and `front_end/src/css/Canvas3D.css`. Its camera framing is bounds/FOV/aspect-based; GSAP transitions use `expo.out`; the blur overlay follows the projected selection with CSS radial-mask variables. When the GLB changes, preserve that behavior and replace only the model-specific loading, name mapping, and hit-to-structure resolution needed to reconnect it. Do not rewrite report generation, questionnaire behavior, or unrelated app layout as part of this skill.
