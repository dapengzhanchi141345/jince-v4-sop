$ErrorActionPreference = 'SilentlyContinue'
$out = 'E:\workbuddy\.wb_roaming_report.txt'
$lines = New-Object System.Collections.Generic.List[string]

function Measure-Dir($path) {
    if (-not (Test-Path -LiteralPath $path)) { return -1 }
    try {
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        $bytes = 0L
        $stack = New-Object System.Collections.Stack
        $stack.Push($path)
        $cnt = 0
        while ($stack.Count -gt 0) {
            $dir = $stack.Pop()
            foreach ($f in [System.IO.Directory]::EnumerateFiles($dir, '*', [System.IO.SearchOption]::TopDirectoryOnly)) {
                try { $bytes += (Get-Item -LiteralPath $f -Force).Length } catch {}
                $cnt++
            }
            foreach ($d in [System.IO.Directory]::EnumerateDirectories($dir, '*', [System.IO.SearchOption]::TopDirectoryOnly)) {
                $stack.Push($d)
            }
        }
        return $bytes
    } catch { return -2 }
}

$targets = @(
    "$env:APPDATA",
    "$env:LOCALAPPDATA"
)
foreach ($root in $targets) {
    $lines.Add("ROOT: $root")
    if (Test-Path -LiteralPath $root) {
        $items = Get-ChildItem -LiteralPath $root -Force -Directory | Sort-Object Name
        $results = @()
        foreach ($d in $items) {
            $sz = Measure-Dir $d.FullName
            if ($sz -ge 0) {
                $results += [PSCustomObject]@{ Name = $d.Name; MB = [math]::Round($sz/1MB,0) }
            }
        }
        $results | Sort-Object MB -Descending | ForEach-Object {
            $lines.Add(("{0,8} MB  {1}" -f $_.MB, $_.Name))
        }
    }
    $lines.Add('')
}

[System.IO.File]::WriteAllLines($out, $lines, [System.Text.Encoding]::UTF8)
Write-Output 'ROAMING_SCAN_DONE'
