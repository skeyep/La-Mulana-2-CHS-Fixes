param([ValidateSet('Install','Check','Restore')][string]$Mode='Install',[string]$GameDirectory,[switch]$NoPause)
$ErrorActionPreference='Stop'

function Hash-File([string]$Path) {
    $stream=[IO.File]::OpenRead($Path);$sha=[Security.Cryptography.SHA256]::Create()
    try { ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-','').ToLowerInvariant() }
    finally { $sha.Dispose();$stream.Dispose() }
}
function Find-Game {
    if ($GameDirectory) { return [IO.Path]::GetFullPath($GameDirectory) }
    $roots=@()
    foreach ($key in @('HKCU:\Software\Valve\Steam','HKLM:\SOFTWARE\WOW6432Node\Valve\Steam')) {
        if (Test-Path $key) { $v=Get-ItemProperty $key; if($v.SteamPath){$roots+=$v.SteamPath};if($v.InstallPath){$roots+=$v.InstallPath} }
    }
    $libraries=@($roots)
    foreach($root in $roots) {
        $vdf=Join-Path $root 'steamapps\libraryfolders.vdf'
        if(Test-Path -LiteralPath $vdf) { foreach($m in [regex]::Matches((Get-Content -Raw -LiteralPath $vdf),'"path"\s*"([^"]+)"')) { $libraries+=$m.Groups[1].Value.Replace('\\','\') } }
    }
    $found=@($libraries | Select-Object -Unique | ForEach-Object { Join-Path $_ 'steamapps\common\La-Mulana 2' } | Where-Object { Test-Path -LiteralPath (Join-Path $_ 'LaMulana2.exe') })
    if($found.Count -eq 1){return $found[0]}
    Add-Type -AssemblyName System.Windows.Forms
    $dialog=New-Object System.Windows.Forms.FolderBrowserDialog;$dialog.Description='Select the La-Mulana 2 folder containing LaMulana2.exe'
    if($dialog.ShowDialog() -ne 'OK'){throw 'No game folder selected.'};return $dialog.SelectedPath
}

$codec=@'
using System;
using System.IO;
using System.IO.Compression;
using System.Security.Cryptography;
public static class LM2Delta {
 static byte[] Exact(BinaryReader r,int n) { var b=r.ReadBytes(n);if(b.Length!=n)throw new EndOfStreamException();return b; }
 public static void Apply(string patch,string output,string[] sources) {
  var inputs=new FileStream[sources.Length];
  try {
   for(int i=0;i<sources.Length;i++)inputs[i]=File.OpenRead(sources[i]);
   using(var raw=File.OpenRead(patch))using(var gz=new GZipStream(raw,CompressionMode.Decompress))using(var r=new BinaryReader(gz))using(var dst=File.Create(output)) {
    if(System.Text.Encoding.ASCII.GetString(Exact(r,8))!="L2DELTA1")throw new InvalidDataException("Invalid patch header");
    long expected=r.ReadInt64();byte[] buffer=new byte[65536];
    while(true) {
     int op=r.ReadByte();if(op==255)break;
     if(op==0) { int n=r.ReadInt32();var b=Exact(r,n);dst.Write(b,0,b.Length); }
     else if(op==1 || op==2) {
      int id=r.ReadByte();long off=r.ReadInt64();int n=r.ReadInt32();var src=inputs[id];src.Position=off;
      while(n>0) {
       int k=Math.Min(n,buffer.Length);int got=0;while(got<k){int q=src.Read(buffer,got,k-got);if(q==0)throw new EndOfStreamException();got+=q;}
       if(op==2){var delta=Exact(r,k);for(int j=0;j<k;j++)buffer[j]^=delta[j];}
       dst.Write(buffer,0,k);n-=k;
      }
     } else throw new InvalidDataException("Unknown patch operation");
    }
    if(dst.Length!=expected)throw new InvalidDataException("Output length mismatch");
   }
  } finally {foreach(var s in inputs)if(s!=null)s.Dispose();}
 }
 public static string SegmentHash(string file,long offset,int length) {
  using(var f=File.OpenRead(file))using(var sha=SHA256.Create()) {
   f.Position=offset;byte[] b=new byte[length];int at=0;while(at<length){int n=f.Read(b,at,length-at);if(n==0)throw new EndOfStreamException();at+=n;}
   return BitConverter.ToString(sha.ComputeHash(b)).Replace("-","").ToLowerInvariant();
  }
 }
}
'@

try {
    $game=Find-Game
    if(!(Test-Path -LiteralPath (Join-Path $game 'LaMulana2.exe'))){throw 'LaMulana2.exe was not found in the selected folder.'}
    foreach($p in @(Get-Process LaMulana2 -ErrorAction SilentlyContinue)) { if($p.Path -and [IO.Path]::GetFullPath($p.Path) -eq (Join-Path $game 'LaMulana2.exe')){throw 'Close La-Mulana 2 before installing, checking, or restoring.'} }
    $stateDir=Join-Path $game '.lm2chs-fixes';$stateFile=Join-Path $stateDir 'installed.json';$transaction=Join-Path $stateDir 'transaction.json'
    if(Test-Path -LiteralPath $transaction) {
        $recover=Get-Content -Raw -LiteralPath $transaction | ConvertFrom-Json
        foreach($f in $recover.files){Copy-Item -LiteralPath $f.rollback -Destination (Join-Path $game $f.path) -Force}
        Remove-Item -LiteralPath $transaction
        Write-Host 'Recovered the interrupted installation to its previous files.'
    }
    if($Mode -eq 'Restore') {
        $restore=Join-Path $stateDir 'Restore.ps1';if(!(Test-Path -LiteralPath $restore)){throw 'No original backup was found.'}
        & $restore -NoPause:$NoPause
        if($LASTEXITCODE -and $LASTEXITCODE -ne 0){throw 'Restore failed.'};exit 0
    }
    $manifest=Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $PSScriptRoot 'Data\manifest.json') | ConvertFrom-Json
    $installed=$null;if(Test-Path -LiteralPath $stateFile){$installed=Get-Content -Raw -LiteralPath $stateFile | ConvertFrom-Json}
    if($Mode -eq 'Check') {
        foreach($f in $manifest.files) {
            $hash=Hash-File (Join-Path $game $f.path)
            if($hash -eq $f.target_hash){Write-Host "PATCHED: $($f.path)"}
            elseif($hash -eq $f.base_hash){Write-Host "ORIGINAL: $($f.path)"}
            else{throw "Unrecognized file: $($f.path). Restore other mods or verify the game in Steam."}
        }
        Write-Host "Check completed for CHS Fixes $($manifest.version).";exit 0
    }
    Add-Type -TypeDefinition $codec -Language CSharp
    New-Item -ItemType Directory -Force -Path $stateDir,(Join-Path $stateDir 'original'),(Join-Path $stateDir 'staging'),(Join-Path $stateDir 'rollback') | Out-Null
    $sourcePaths=@($manifest.sources | ForEach-Object {Join-Path $game $_})
    foreach($f in $manifest.files) {
        $path=Join-Path $game $f.path;$hash=Hash-File $path;$old=$null
        if($installed){$old=@($installed.files | Where-Object {$_.path -eq $f.path})[0]}
        if($hash -ne $f.base_hash -and $hash -ne $f.target_hash -and (!$old -or $hash -ne $old.target_hash)){throw "Unsupported or modified game file: $($f.path). Verify the game in Steam first."}
        $backup=Join-Path $stateDir ('original\'+[IO.Path]::GetFileName($f.path))
        if(!(Test-Path -LiteralPath $backup)) {if($hash -ne $f.base_hash){throw 'An original backup is required before installing over a patched file.'};Copy-Item -LiteralPath $path -Destination $backup}
        if((Hash-File $backup) -ne $f.base_hash){throw "Original backup mismatch: $backup"}
        $sourcePaths[$f.source_index]=$backup
    }
    foreach($seg in $manifest.source_segments) {if([LM2Delta]::SegmentHash($sourcePaths[$seg.source_index],$seg.offset,$seg.length) -ne $seg.sha256){throw 'The original font atlas data does not match this game build.'}}
    $txnFiles=@()
    foreach($f in $manifest.files) {
        $name=[IO.Path]::GetFileName($f.path);$staged=Join-Path $stateDir ('staging\'+$name);$rollback=Join-Path $stateDir ('rollback\'+$name)
        [LM2Delta]::Apply((Join-Path $PSScriptRoot ('Data\'+$f.patch)),$staged,[string[]]$sourcePaths)
        if((Hash-File $staged) -ne $f.target_hash){throw "Patched output verification failed: $name"}
        Copy-Item -LiteralPath (Join-Path $game $f.path) -Destination $rollback -Force
        $txnFiles+=@{path=$f.path;rollback=$rollback;staged=$staged}
    }
    @{files=$txnFiles} | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 -LiteralPath $transaction
    try {
        foreach($f in $txnFiles){[IO.File]::Replace($f.staged,(Join-Path $game $f.path),$f.rollback)}
        $manifest | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 -LiteralPath $stateFile
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'Restore-Standalone.ps1') -Destination (Join-Path $stateDir 'Restore.ps1') -Force
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'Restore-Standalone.cmd') -Destination (Join-Path $stateDir 'Restore.cmd') -Force
        Remove-Item -LiteralPath $transaction
    } catch {
        foreach($f in $txnFiles){Copy-Item -LiteralPath $f.rollback -Destination (Join-Path $game $f.path) -Force}
        throw
    }
    Write-Host "Installed LA-MULANA 2 CHS Fixes $($manifest.version). Select Chinese in game."
    Write-Host "Independent restore: $stateDir\Restore.cmd"
} catch { Write-Host ('ERROR: '+$_.Exception.Message);exit 1 }
