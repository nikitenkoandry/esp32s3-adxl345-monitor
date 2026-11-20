# Draw matching PNG and SVG connection diagrams without external dependencies.
# Terminal positions are schematic, not the physical header order.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$projectDir = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$outputDir = Join-Path $projectDir 'docs\images'
[System.IO.Directory]::CreateDirectory($outputDir) | Out-Null
$canvasWidth = 1800
$canvasHeight = 1120
$bitmap = [System.Drawing.Bitmap]::new($canvasWidth, $canvasHeight)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$graphics.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
$svg = [System.Collections.Generic.List[string]]::new()
$svg.Add('<svg xmlns="http://www.w3.org/2000/svg" width="1800" height="1120" viewBox="0 0 1800 1120" role="img" aria-labelledby="title description">')
$svg.Add('<title id="title">ADXL345 to ESP32-S3 SPI wiring</title>')
$svg.Add('<desc id="description">VCC to 3V3, GND to GND, SCLK to GPIO12, SDA or SDI to GPIO11, SDO to GPIO13, CS to GPIO10, and INT1 to GPIO4. Use the USB-UART connector to the PC at 921600 baud. Terminal positions are schematic.</desc>')

function Draw-Rect($x, $y, $w, $h, $fill, $stroke = '', $strokeWidth = 1) {
    $brush = [System.Drawing.SolidBrush]::new([System.Drawing.ColorTranslator]::FromHtml($fill))
    $graphics.FillRectangle($brush, [single]$x, [single]$y, [single]$w, [single]$h)
    $brush.Dispose()
    $outline = ''
    if ($stroke) {
        $pen = [System.Drawing.Pen]::new([System.Drawing.ColorTranslator]::FromHtml($stroke), [single]$strokeWidth)
        $graphics.DrawRectangle($pen, [single]$x, [single]$y, [single]$w, [single]$h)
        $pen.Dispose()
        $outline = " stroke='$stroke' stroke-width='$strokeWidth'"
    }
    $svg.Add("<rect x='$x' y='$y' width='$w' height='$h' fill='$fill'$outline/>")
}

function Draw-Line($x1, $y1, $x2, $y2, $color, $width = 3) {
    $pen = [System.Drawing.Pen]::new([System.Drawing.ColorTranslator]::FromHtml($color), [single]$width)
    $pen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
    $pen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
    $graphics.DrawLine($pen, [single]$x1, [single]$y1, [single]$x2, [single]$y2)
    $pen.Dispose()
    $svg.Add("<line x1='$x1' y1='$y1' x2='$x2' y2='$y2' stroke='$color' stroke-width='$width' stroke-linecap='round'/>")
}

function Draw-Text($x, $y, $value, $size = 24, $color = '#172B40', $bold = $false, $center = $false) {
    $style = [System.Drawing.FontStyle]::Regular
    if ($bold) { $style = [System.Drawing.FontStyle]::Bold }
    $font = [System.Drawing.Font]::new('Segoe UI', [single]$size, $style, [System.Drawing.GraphicsUnit]::Pixel)
    $brush = [System.Drawing.SolidBrush]::new([System.Drawing.ColorTranslator]::FromHtml($color))
    $left = [single]$x
    if ($center) { $left -= $graphics.MeasureString($value, $font).Width / 2 }
    $graphics.DrawString($value, $font, $brush, $left, [single]($y - $size * 1.02))
    $weight = '400'
    if ($bold) { $weight = '700' }
    $anchor = 'start'
    if ($center) { $anchor = 'middle' }
    $escaped = [System.Security.SecurityElement]::Escape($value)
    $svg.Add("<text x='$x' y='$y' font-family='Segoe UI,Arial,sans-serif' font-size='$size' font-weight='$weight' text-anchor='$anchor' fill='$color'>$escaped</text>")
    $brush.Dispose()
    $font.Dispose()
}

function Draw-Dot($x, $y, $radius, $color) {
    $brush = [System.Drawing.SolidBrush]::new([System.Drawing.ColorTranslator]::FromHtml($color))
    $graphics.FillEllipse($brush, [single]($x - $radius), [single]($y - $radius), [single]($radius * 2), [single]($radius * 2))
    $brush.Dispose()
    $svg.Add("<circle cx='$x' cy='$y' r='$radius' fill='$color'/>")
}

function Draw-Arrow($x, $y, $direction, $color) {
    $back = $x - 15 * $direction
    Draw-Line $back ($y - 8) $x $y $color 4
    Draw-Line $back ($y + 8) $x $y $color 4
}

Draw-Rect 0 0 1800 1120 '#F4F7FB'
Draw-Rect 0 0 1800 166 '#0E2034'
Draw-Text 80 76 'ADXL345 + ESP32-S3' 44 '#FFFFFF' $true
Draw-Text 80 125 'SPI wiring for the ESP-IDF acceleration monitor' 25 '#B6C9DD'
Draw-Rect 1355 51 365 58 '#1E3A53'
Draw-Text 1537 90 '7 wires  /  3.3 V logic' 24 '#FFFFFF' $true $true

# Functional terminal blocks, deliberately not physical footprints.
Draw-Rect 80 220 480 665 '#FFFFFF' '#D5E0EB' 2
Draw-Rect 80 220 480 100 '#E3F4EB'
Draw-Text 112 268 'ADXL345' 33 '#176B4A' $true
Draw-Text 112 302 '3-axis accelerometer module' 21 '#36715A'
Draw-Rect 1240 220 480 665 '#FFFFFF' '#D5E0EB' 2
Draw-Rect 1240 220 480 100 '#E4EEFA'
Draw-Text 1272 268 'ESP32-S3' 33 '#17568D' $true
Draw-Text 1272 302 'DevKitC-1  /  16 MB flash' 21 '#3E6387'

$connections = @(
    @{ Sensor='VCC / 3V3'; Board='3V3'; Label='3.3 V power'; Color='#D34047'; Direction=-1 },
    @{ Sensor='GND'; Board='GND'; Label='Common ground'; Color='#526375'; Direction=0 },
    @{ Sensor='SCLK / SCL'; Board='GPIO12'; Label='SPI clock'; Color='#2974D5'; Direction=-1 },
    @{ Sensor='SDA / SDI'; Board='GPIO11'; Label='MOSI  |  ESP to sensor'; Color='#12805D'; Direction=-1 },
    @{ Sensor='SDO'; Board='GPIO13'; Label='MISO  |  sensor to ESP'; Color='#07849D'; Direction=1 },
    @{ Sensor='CS'; Board='GPIO10'; Label='Chip select'; Color='#BC6A10'; Direction=-1 },
    @{ Sensor='INT1'; Board='GPIO4'; Label='FIFO interrupt  |  required'; Color='#8A4DCE'; Direction=1 }
)
for ($i = 0; $i -lt $connections.Count; $i++) {
    $row = $connections[$i]
    $y = 374 + $i * 72
    if ($i % 2 -eq 0) {
        Draw-Rect 96 ($y - 31) 446 59 '#F3F7FA'
        Draw-Rect 1258 ($y - 31) 444 59 '#F3F7FA'
    }
    Draw-Text 115 ($y + 8) $row.Sensor 27 '#172B40' $true
    Draw-Text 1280 ($y + 8) $row.Board 27 '#172B40' $true
    Draw-Line 560 $y 1240 $y $row.Color 5
    Draw-Dot 560 $y 9 $row.Color
    Draw-Dot 1240 $y 9 $row.Color
    Draw-Text 900 ($y - 15) $row.Label 23 $row.Color $true $true
    if ($row.Direction -ne 0) { Draw-Arrow 900 $y $row.Direction $row.Color }
}
Draw-Text 112 858 'INT2: leave unconnected' 20 '#61768B'
Draw-Text 1272 858 'USB-UART connector to the PC' 20 '#17568D' $true

Draw-Rect 80 924 800 95 '#FFF3DE' '#EBD7B3' 1
Draw-Text 104 962 'Use 3.3 V power and logic' 25 '#865000' $true
Draw-Text 104 998 'Disconnect power while wiring. Keep signal wires short.' 21 '#865000'
Draw-Rect 904 924 816 95 '#E4EEFA' '#C8DAEE' 1
Draw-Text 928 962 'USB-UART to Windows monitor  |  921600 baud' 24 '#17568D' $true
Draw-Text 928 998 'SPI: mode 3, 2 MHz  |  ADXL345: nominal 800 Hz' 21 '#17568D'
Draw-Text 80 1060 'Terminal positions are schematic. Follow the printed pin labels on your boards.' 22 '#526375'
Draw-Text 80 1093 'SDA / SDI is MOSI in SPI mode; SDO is MISO. INT1 must connect to GPIO4.' 20 '#526375'

$svg.Add('</svg>')
$pngPath = Join-Path $outputDir 'wiring-esp32s3-adxl345.png'
$svgPath = Join-Path $outputDir 'wiring-esp32s3-adxl345.svg'
$bitmap.Save($pngPath, [System.Drawing.Imaging.ImageFormat]::Png)
[System.IO.File]::WriteAllLines($svgPath, $svg, [System.Text.UTF8Encoding]::new($false))
$graphics.Dispose()
$bitmap.Dispose()
Write-Output $pngPath
Write-Output $svgPath
