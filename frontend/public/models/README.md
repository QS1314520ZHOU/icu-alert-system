# Human Body GLB Asset Preparation

This folder is reserved for manually prepared assets:

- `human_high.glb`: desktop high model, target under 8 MB after Draco compression.
- `human_low.glb`: low model, target under 2 MB.
- `human_body.svg`: SVG fallback with the same organ ids used by the frontend.

## Z-Anatomy To GLB Workflow

1. Download the Z-Anatomy source package according to its license.
2. Open the model in Blender.
3. Keep only ICU-relevant organs:
   - heart
   - left lung
   - right lung
   - liver
   - left kidney
   - right kidney
   - brain
   - stomach
   - intestine
   - spleen
   - pancreas
   - bladder
4. Rename meshes using the Latin names expected by `ORGAN_MAP`:
   - `Cor`
   - `Pulmo_sinister`
   - `Pulmo_dexter`
   - `Hepar`
   - `Ren_sinister`
   - `Ren_dexter`
   - `Cerebrum`
   - `Gaster`
   - `Intestinum`
   - `Lien`
   - `Pancreas`
   - `Vesica_urinaria`
5. Apply transforms and set model origin near the body center.
6. Add a Decimate Modifier:
   - high model: ratio around `0.35` to `0.55`, target under 400k triangles.
   - low model: ratio around `0.08` to `0.18`, target under 80k triangles.
7. Use simple materials only. Do not add HDRI, PBR texture sets, or post-processing assets.
8. Export GLB:
   - Format: `glTF Binary (.glb)`
   - Include: selected objects
   - Transform: +Y up as needed after visual verification
   - Geometry: apply modifiers
   - Materials: export simple materials
9. Compress with Draco:

```bash
npx gltf-pipeline -i human_high_raw.glb -o human_high.glb -d
npx gltf-pipeline -i human_low_raw.glb -o human_low.glb -d
```

10. Place the files in this folder and test:

```bash
npm run dev
```

Then open `/demo/human-body?force=high` and `/demo/human-body?force=low`.

## Naming Contract

The frontend maps backend business organ names to GLB mesh names and SVG ids in:

`src/components/HumanBody/constants/organMap.ts`

Changing mesh names in Blender requires updating that file and its unit tests.
