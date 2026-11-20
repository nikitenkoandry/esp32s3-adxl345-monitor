# Photo-based wiring illustration

Asset: `docs/images/wiring-esp32s3-adxl345-photo.png`.

Created with the built-in `image_gen` tool, followed by visual review and two
corrections. This is an illustration, not a photograph of the user's assembled
hardware. Sensor terminal positions are illustrative; follow the module labels.
The seven connections match `firmware/main/board_config.h` and the existing
logical diagram. The left DevKitC-1 J1 header is shown with 22 pins.

## References

- [Official board guide and J1 pin table](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitc-1/user_guide_v1.1.html).
- [Official Espressif board photo](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/_images/esp32-s3-devkitc-1-v1.1-isometric.png).
- [Official Espressif pin layout](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/_images/ESP32-S3_DevKitC-1_pinlayout_v1.1.jpg).
- Project wiring diagram: `docs/images/wiring-esp32s3-adxl345.png`.

The official board images were visual/layout references. The final artwork is
generated and was not captured from the physical project hardware.

## Initial generation

```text
Use case: scientific-educational / infographic-diagram.
Create a polished, technically precise photo-based wiring infographic for a GitHub hardware project, landscape 3:2, high resolution. English typography.

REFERENCES:
Image 1 is the official Espressif ESP32-S3-DevKitC-1 board photograph, a visual reference for the real black PCB, metal ESP32-S3-WROOM shield, antenna, two 22-pin headers, two Micro-USB sockets, BOOT and RESET buttons.
Image 2 is the official board pin-layout reference and is the AUTHORITY for physical ESP pin positions. Do not copy its long alternate-function text.
Image 3 is the project's logical wiring diagram, the AUTHORITY for the seven connections and wire colors.

COMPOSITION:
Clean light background, dark navy title strip reading "ADXL345 + ESP32-S3" and smaller subtitle "SPI + INT1 wiring". Large realistic top-down ESP32-S3-DevKitC-1 board on the RIGHT, antenna pointing UP and USB sockets DOWN. Depict the REAL board based on reference 1 and follow the 22-pin header order from reference 2. On the LEFT show a smaller blue ADXL345 breakout board or sensor illustration, with a neat adjacent group of seven clearly named sensor connection points; positions of sensor terminals may be schematic and must be called out as such. Use seven colored wires with clearly separated routes and labeled endpoint callouts. Choose sensor terminal ordering top-to-bottom to minimize crossings: VCC, INT1, CS, SDA/SDI, SCLK/SCL, SDO, GND. Any extra INT2 terminal is disconnected.

EXACT CONNECTIONS, ONLY SEVEN WIRES:
RED: sensor VCC -> ESP 3V3, topmost LEFT header pin J1.1.
PURPLE: sensor INT1 -> ESP GPIO4, FOURTH pin from top in LEFT header, J1.4.
ORANGE: sensor CS -> ESP GPIO10, SIXTEENTH pin from top in LEFT header, J1.16.
GREEN: sensor SDA/SDI (MOSI) -> ESP GPIO11, SEVENTEENTH pin from top in LEFT header, J1.17.
BLUE: sensor SCLK/SCL -> ESP GPIO12, EIGHTEENTH pin from top in LEFT header, J1.18.
CYAN: sensor SDO (MISO) -> ESP GPIO13, NINETEENTH pin from top in LEFT header, J1.19.
DARK GRAY: sensor GND -> ESP GND, BOTTOMMOST LEFT header pin J1.22.
Use a colored dot exactly on each of those selected physical ESP header pins. The FOUR SPI pins GPIO10, 11, 12, 13 must be FOUR adjacent pins in this order, immediately above GPIO14, 5V, GND at the bottom of the left header.
Never connect anything to 5V, EN/RST, or GPIO9. Leave the whole right-side ESP header unused.
Show only clearly legible printed labels on the board; selected pins have large external callouts so they are unambiguous.

At the bottom of the board point to the LEFT Micro-USB socket (marked UART) with "USB-UART to PC | 921600 baud". Right Micro-USB socket is native USB and unused for this project's stream.
Include a compact exact legend/table: "3V3 -> VCC", "GPIO4 -> INT1", "GPIO10 -> CS", "GPIO11 -> SDA/SDI (MOSI)", "GPIO12 -> SCLK/SCL", "GPIO13 <- SDO (MISO)", "GND -> GND". Prefer simple connection dashes rather than arrows if directions clutter.
Footer text: "3.3 V power and logic | INT1 required | SPI mode 3, 2 MHz | nominal 800 Hz".
Small footnote: "Sensor terminal positions are illustrative. Follow the pin labels on your module."
No imaginary extra connections, no breadboard, no extra devices, no cropped boards, no decorative text. Prioritize correct pin targeting over photorealistic flourishes.
```

## Pin layout correction

```text
Edit Image 1, the photo-based wiring infographic. Image 2 is the authoritative reference for the physical ESP32-S3-DevKitC-1 pin header arrangement.

CRITICAL CORRECTION ONLY: Image 1 incorrectly has about 18 visible pads in the ESP left header, and its GPIO callouts are on physically wrong pins. Replace/redraw the ESP board and nearest wire endpoint labels as necessary so it has EXACTLY TWENTY-TWO uniformly spaced pins on EACH side, like Image 2. This correction is essential; it is a wiring instruction. Keep the sensor, table, title, footer, wire color mapping and overall polished appearance.

Top view, antenna up, two Micro-USB ports down. The LEFT header top-to-bottom, no omissions, no extra pad above/below:
1 3V3 (RED wire), 2 3V3, 3 RST, 4 GPIO4 (PURPLE wire), 5 GPIO5, 6 GPIO6, 7 GPIO7, 8 GPIO15, 9 GPIO16, 10 GPIO17, 11 GPIO18, 12 GPIO8, 13 GPIO3, 14 GPIO46, 15 GPIO9, 16 GPIO10 (ORANGE wire), 17 GPIO11 (GREEN wire), 18 GPIO12 (BLUE wire), 19 GPIO13 (CYAN wire), 20 GPIO14 (unused), 21 5V (unused), 22 GND (GRAY wire).
Only seven colored connections, each ends in a colored dot on exactly its numbered physical pad. No wire on RST, GPIO9, GPIO14 or 5V. No wires on right header. There must be TWO unused pads between red 3V3 and purple GPIO4. There must be ELEVEN unused pads between purple GPIO4 and orange GPIO10. Orange/green/blue/cyan are consecutive pins 16/17/18/19. Then TWO unused pins 20/21, then gray ground pin 22. Do not place any additional pin above the red first pin.

For the existing 1536 x 1024 composition, the left column can run from y=150 (first red pin) to y=744 (22nd gray pin), exactly 22 pads spaced about 28.286 pixels. Thus purple at y=235; orange at y=574; green at y=603; blue at y=631; cyan at y=659; ground at y=744. You may enlarge the board/composition slightly if needed for legibility. Reposition label boxes and reroute colored wires to match these corrected endpoints; never let text obscure the pin count. These coordinates explain the necessary physical distribution, not text to print.

The right header also has 22 pins. Use the physical board from reference 2 for its pad count and layout; do not invent a shorter 18-pin board. USB-UART is the bottom LEFT USB socket.

Keep the exact correct mapping table. Keep the note "Sensor terminal positions are illustrative. Follow the pin labels on your module."
No other edits.
```

## Final correction

```text
Make THREE tiny precise corrections to this image, preserving all other pixels, layout, text, colors, wires, selected pin positions and board appearance as closely as possible.

1. Remove the single EXTRA unconnected gold circular solder pad at the very TOP of the LEFT board header, centered at approximately x=976,y=133 in this 1536x1024 image. Replace just that small extra pad with plain dark PCB. The red 3V3 pad centered at x=976,y=160 must be the TOPMOST physical header pin. Keep that red pad and its wire in place.
2. Remove the matching EXTRA topmost unconnected gold circular solder pad on the RIGHT board header, centered approximately x=1260,y=133. Replace it with dark PCB too. First right header pad must be at y=160. Do not change the other 22 pads on either side. After this there are exactly 22 pins on each header; do not add new pads elsewhere.
3. Fix the gray external label immediately below "J1.12 GPIO8" and immediately above "J1.14 GPIO46" to read EXACTLY "J1.13   GPIO3". Currently its number is garbled. Only fix this one label's characters.

Everything else stays unchanged. In particular preserve all seven wires and their exact endpoints, all other J1 labels, the correct table, realistic sensor, title, USB labels and footer. Do not redesign, reposition or regenerate the diagram.
```
