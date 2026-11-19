$out = 'E:\workbuddy\.wb_subdir_sizes.txt'
$lines = New-Object System.Collections.Generic.List[string]
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
$targets = @(
    'C:\Users\ASUS\AppData\Roaming\TRAE SOLO CN',
    'C:\Users\ASUS\AppData\Local\hermes'
)
foreach ($t in $targets) {
    $lines.Add("ROOT: $t")
    $dirs = Get-ChildItem -LiteralPath $t -Force -Directory | Select-Object -ExpandProperty Name
    foreach ($n in $dirs) {
        $mb = Get-SizeMB (Join-Path $t $n)
        $lines.Add(("{0,8} MB  {1}" -f $mb, $n))
    }
    $lines.Add('')
}
[System.IO.File]::WriteAllLines($out, $lines, [System.Text.Encoding]::UTF8)
Write-Output 'SUBDIR_DONE'
