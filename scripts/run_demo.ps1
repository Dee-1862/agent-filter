<#
 Windows wrapper for python -m otr.app.
   .\scripts\run_demo.ps1 replay                 # scripted demo, no downloads
   .\scripts\run_demo.ps1 audio [-Audio PATH...] # per-speaker WAVs (default demo_audio; made by make_demo_audio.py if absent)
   .\scripts\run_demo.ps1 livekit                # per-person consent mode (starts LiveKit via docker compose)
   .\scripts\run_demo.ps1 livekit-stream
 Options: -Llm none|ollama[:MODEL]  -Hold 10  -Speed 1  -Port 8000  -Model tiny.en  -Turns file.json  -Check
#>
param(
  [ValidateSet('replay','audio','livekit','livekit-stream')][string]$Source = 'replay',
  [string[]]$Audio,
  [string]$Turns,
  [string]$Script = 'demo\scripts\demo_main.txt',
  [string]$Llm = 'none',
  [double]$Hold = 10,
  [double]$Speed = 1,
  [int]$Port = 8000,
  [string]$Model,
  [switch]$Check
)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
if (Test-Path '.venv\Scripts\python.exe') { $py = '.venv\Scripts\python.exe' } else { $py = 'python' }

$a = @('-m','otr.app','--source',$Source,'--llm',$Llm,'--hold',$Hold,'--speed',$Speed,'--port',$Port)
if ($Source -eq 'replay') { $a += @('--script',$Script) }
if ($Source -eq 'audio') {
  if (-not $Audio) {
    if (-not (Test-Path 'demo_audio')) {
      Write-Host 'No -Audio given and demo_audio\ missing: generating it with local Windows TTS...'
      & $py scripts\make_demo_audio.py
      if ($LASTEXITCODE -ne 0) { Write-Host 'No TTS available. Pass -Audio <folder or wavs>.'; exit 3 }
    }
    $Audio = @('demo_audio')
  }
  $a += @('--audio') + $Audio
  if ($Turns) { $a += @('--turns',$Turns) }
}
if ($Model) { $a += @('--model',$Model) }
if ($Check) { $a += '--check' }
& $py @a
exit $LASTEXITCODE
