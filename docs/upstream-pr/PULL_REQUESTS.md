# Pull requests: BK7252N camera support

Two PRs, in this order:

1. **SDK**: `0001-sdk-camera_intf-build-on-BK7252N-and-add-GC0329.patch`
   targets `NonPIayerCharacter/beken_freertos_sdk` (`master`). OpenBeken pulls this repository in
   as the `sdk/beken_freertos_sdk` submodule.
2. **OpenBeken**: `0002-obk-BK7252N-add-BKCam-driver.patch`
   targets `openshwprojects/OpenBK7231T_App` (`main`), with the submodule bumped to the merged
   PR 1.

Both patches apply cleanly to OpenBeken `168cba55` and SDK `f5a64d4` (checked with
`git apply --check`). Tested on the camera: a clean checkout plus these two patches; the only
bench change was the console on UART1.

## Submitting (GitHub CLI)

```sh
# --- PR 1: SDK
cd ~/cam/OpenBK7231T_App/sdk/beken_freertos_sdk
gh repo fork NonPIayerCharacter/beken_freertos_sdk --remote --remote-name fork
git switch -c bk7252n-camera-gc0329
git am ~/cam/bk7252-cam/openbk-port/pr/0001-sdk-camera_intf-build-on-BK7252N-and-add-GC0329.patch
git push -u fork bk7252n-camera-gc0329
gh pr create --repo NonPIayerCharacter/beken_freertos_sdk --base master \
  --title "camera_intf: build on BK7252N and add GC0329/GC0329C support" \
  --body-file ~/cam/bk7252-cam/openbk-port/pr/PR1_body.md

# --- PR 2: OpenBeken
cd ~/cam/OpenBK7231T_App
gh repo fork openshwprojects/OpenBK7231T_App --remote --remote-name fork
git switch -c bk7252n-bkcam
git am ~/cam/bk7252-cam/openbk-port/pr/0002-obk-BK7252N-add-BKCam-driver.patch
# After PR 1 is merged, point the submodule at it:
#   (cd sdk/beken_freertos_sdk && git fetch origin && git checkout <merged commit>)
#   git add sdk/beken_freertos_sdk && git commit -m "Bump beken_freertos_sdk: camera_intf on BK7252N, GC0329"
git push -u fork bk7252n-bkcam
gh pr create --repo openshwprojects/OpenBK7231T_App --base main \
  --title "BK7252N: add BKCam driver (DVP camera, JPEG snapshot and MJPEG stream)" \
  --body-file ~/cam/bk7252-cam/openbk-port/pr/PR2_body.md
```

`git am` applies both patches as commits authored by you (im486dx). The messages carry a
Co-Authored-By trailer for Claude.

## Before submitting, please check

- **Where the GC0329 table came from.** The 259 register values were read out of the factory
  firmware of your camera. They are configuration data rather than code, and similar GC0329
  tables appear in many open-source drivers. The commit wording is neutral ("taken from a BK7252N
  camera that ships with this sensor"), but you decide whether you're comfortable contributing it.
- **The upstream default branch** (`main` / `master`). Confirm it on GitHub before `gh pr create`.

## Left out on purpose (specific to this camera)

| Change | Why not upstream |
|---|---|
| Console on UART1 (`uart_print_port`) | depends on which UART a board brings out |
| DPLL-calibration helpers in ITCM (`bk7252n_bsp.lds`) | not needed when the board has proper power |
| Auto-enabling "accept UART commands" | silently changes user settings |
| Auto-starting BKCam | normal OpenBeken practice is `startDriver BKCam` |
| Version label on the camera page | the build version is already on OpenBeken's page |
