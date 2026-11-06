param([switch]$NoPause)
$ErrorActionPreference='Stop'
function Hash-File([string]$Path) {
 $stream=[IO.File]::OpenRead($Path);$sha=[Security.Cryptography.SHA256]::Create()
 try { ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-','').ToLowerInvariant() }
 finally {$sha.Dispose();$stream.Dispose()}
}
try {
 $game=Split-Path $PSScriptRoot -Parent;$state=Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot 'installed.json') | ConvertFrom-Json
 if(Test-Path -LiteralPath (Join-Path $PSScriptRoot 'linux-transaction.json')){throw 'A Linux operation was interrupted. Run Restore.sh on Linux to recover it first.'}
 foreach($p in @(Get-Process LaMulana2 -ErrorAction SilentlyContinue)){if($p.Path -eq (Join-Path $game 'LaMulana2.exe')){throw 'Close La-Mulana 2 before restoring.'}}
 foreach($f in $state.files){
  $backup=Join-Path $PSScriptRoot ('original\'+[IO.Path]::GetFileName($f.path))
  if((Hash-File $backup) -ne $f.base_hash){throw "Original backup mismatch: $backup"}
 }
 foreach($f in $state.files){Copy-Item -LiteralPath (Join-Path $PSScriptRoot ('original\'+[IO.Path]::GetFileName($f.path))) -Destination (Join-Path $game $f.path) -Force}
 foreach($f in $state.files){if((Hash-File (Join-Path $game $f.path)) -ne $f.base_hash){throw 'Restored file verification failed.'}}
 Write-Host 'Original game files restored. Saves and configuration were kept.';exit 0
} catch {Write-Host ('ERROR: '+$_.Exception.Message);exit 1}
