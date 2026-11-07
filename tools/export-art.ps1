# Export every .aseprite file under art/ to a PNG sprite sheet + JSON in game/assets/sprites/.
# Folder structure is kept: art/cars/car.aseprite -> game/assets/sprites/cars/car.png
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$art = Join-Path $root 'art'
$out = Join-Path $root 'game\assets\sprites'
$aseprite = 'D:\dev\tools\aseprite\aseprite.exe'
Get-ChildItem $art -Recurse -Filter *.aseprite | ForEach-Object {
  $rel = $_.DirectoryName.Substring($art.Length).TrimStart('\')
  $dest = Join-Path $out $rel
  New-Item -ItemType Directory -Force $dest | Out-Null
  $png = Join-Path $dest ($_.BaseName + '.png')
  $json = Join-Path $dest ($_.BaseName + '.json')
  & $aseprite -b $_.FullName --sheet $png --data $json --format json-array --sheet-type packed --list-tags | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "export failed: $($_.FullName)" }
  Write-Output ("exported " + (Join-Path $rel $_.BaseName))
}
