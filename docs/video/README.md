# Monitor video demo

[View the inline player](../../README.md#video-demo)
or [open the repository MP4](monitor-demo.mp4).

The 22.3-second video combines two screen recordings supplied by the project
author. It shows the Windows monitor connected to ESP32-S3 over USB-UART at
921600 baud:

| Time | What is shown |
| --- | --- |
| 00:00–about 00:11 | Live X, Y and Z acceleration graphs during sensor movement |
| About 00:11–00:22 | Gravity-based 3D tilt, angle readouts and quality messages |

The recording includes fast motion. Orange messages indicate that acceleration
can distort the gravity-based angle estimate. This view does not measure yaw
or reconstruct an XYZ movement path. The recording illustrates the interface;
see [validation notes](../validation.md) for the separate hardware test results.

## Published file

- File: `monitor-demo.mp4`, 3,533,877 bytes.
- Video: H.264, 1916 × 1026, 30 frames/s, 669 frames.
- Duration: 22.3 seconds.
- Audio: none; both source audio tracks were silent.
- SHA-256: `41304f5a26a639612e978d1fcabf97980348814cc3483072edae2e8874f62bb7`.

The file uses MP4 fast-start metadata for browser playback. It is also uploaded
as a GitHub media attachment so the main README can display an inline player.

## Source recordings

The originals remain unchanged in the local `docs/video/` folder and are ignored
by Git. The compact combined recording is versioned for download and reuse.

| Local source | Duration | Original SHA-256 |
| --- | --- | --- |
| `acc_log.mp4` | 10.83 s | `851e344893d95408179b62b44b31709b3876aafa70a772713c225fc8ca688352` |
| `3d_orient.mp4` | 11.47 s | `7e879935b30f2ecfd745149de8a701f7ed702e3d0459fc310fa320b7005f812c` |

Preparation joined the graphs clip first and the 3D clip second, retained the
original frame rate and width, and padded the 3D clip by 22 pixels at the bottom
to match the graph clip's height. H.264 encoding used CRF 20 and the slow preset;
the silent audio tracks and source container metadata were omitted.
