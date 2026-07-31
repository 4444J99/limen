# Danse Installation Specification

This document details the physical requirements and constraints for installing *Danse* in a gallery or museum setting.

## Core Directives
1. **No Mapping Software**: The scene is already fully 3D. The output is a raw video stream derived from the exact physical geometry of the space. Do not use MadMapper, Resolume, or other projection-mapping software to warp the 2D output. Warping discards depth and flattens the artwork.
2. **No Edge-Blending**: The projection beams should overlap, disagree, and fracture. Additive brightness where beams cross is a feature of the work, not an error.
3. **Privacy by Design**: The interactive tracking (MediaPipe) runs locally, on-device. The user's image is never composited onto the screens, saved to disk, or transmitted over the internet. The pose only acts as a query to modulate the generative selection engine.

## Materials
- **Projection Surfaces**: 
  - 20 yd White polyester chiffon/voile (60" width)
  - 3 Frosted PEVA shower liners
  - 10 yd Bridal tulle (Bobbinet)
  - Mylar emergency blanket (use sparingly, crumpled, as HoloGauze equivalent)
  - Vellum roll
- **Rigging**: Tension rods, 40lb monofilament, binder clips, gaff tape. No heavy rigging required. All textiles must be NFPA 701 certified.

## Tier A: Project Space (15×20 ft)
- **Surfaces**: 5 fabric panels at staggered depths (3.5 ft, 5.5 ft, 8 ft, 10.5 ft, 13 ft) and staggered yaw angles (-38°, -14°, +7°, +26°, +49°). One panel should run into a room corner so the image folds at 90°.
- **Projectors**: 2× Panasonic PT-VMZ51 (Optical lens shift is mandatory to keep visitor shadows out of the beam), 1× Optoma ZH450ST. 3LCD is preferred over DLP to avoid rainbow artifacts on moving eyes.
- **Compute**: One Mac mini M4 Pro driving all three outputs.
- **Cost**: ~$18,750 (hardware).

## Tier B: Museum Space (30×40 ft)
- **Cost**: ~$46,000 (rental), ~$90,000 (purchase).

## Lighting & Environment
- **Ambient Light**: Kill every ambient source. Tape over all router LEDs, smoke-detector LEDs, and emergency lights that aren't strictly required by code.
- **Practical Light**: Provide one practical light at 1–2% of projection brightness, bounced off a side wall and never in frame. The room must look like a room, not a void.
- **Backdrop**: Terminate the image in the void. A black sheet must hang behind the last layer. Nothing touches anything.

## Acceptance Criteria
- Pull the wall plug. Wait 4 minutes. If the room does not automatically come back online and resume the generative display without any human input, the installation is not finished.
