param([int]$Slice = 0)
$ErrorActionPreference = 'SilentlyContinue'
$out = ('E:\workbuddy\.wb_roam_slice{0}.txt' -f $Slice)
$lines = New-Object System.Collections.Generic.List[string]
$root = 'C:\Users\ASUS\AppData\Roaming'
$skip = @('CodeBuddyExtension','Microsoft','Adobe','Macromedia','WorkBuddy')
$dirs = Get-ChildItem -LiteralPath $root -Force -Directory | Where-Object { $_.Name -notin $skip } | Select-Object -ExpandProperty Name

function Get-SizeMB($path) {
    if (-not (Test-Path -LiteralPath $path)) { return -1 }
    try {
        $bytes = 0L
        $stack = New-Object System.Collections.Stack
        $stack.Push($path)
        while ($stack.Count -gt 0) {
            $dir = $stack.Pop()
            foreach ($d in [System.IO.Directory]::EnumerateDirectories($dir, '*', [System.IO.SearchOption]::TopDirectoryOnly)) {
                try { $stack.Push($d) } catch {}
            }
            foreach ($f in [System.IO.Directory]::EnumerateFiles($dir, '*', [System.IO.SearchOption]::TopDirectoryOnly)) {
                try { $bytes += (Get-Item -LiteralPath $f -Force).Length } catch {}
            }
        }
        return [math]::Round($bytes/1MB,0)
    } catch { return -2 }
}

$i = 0
foreach ($n in $dirs) {
    if ($i % 4 -ne $Slice) { $i++; continue }
    $i++
    $item = Get-Item -LiteralPath (Join-Path $root $n) -Force
    if ($item.LinkType) { $lines.Add(("J|{0}|0" -f $n)); continue }
    $mb = Get-SizeMB (Join-Path $root $n)
    $lines.Add(("{0}|{1}" -f $n, $mb))
}
[System.IO.File]::WriteAllLines($out, $lines, [System.Text.Encoding]::UTF8)
Write-Output ('SLICE{0}_DONE' -f $Slice)
