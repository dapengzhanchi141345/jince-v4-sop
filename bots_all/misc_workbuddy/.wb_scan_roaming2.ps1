$ErrorActionPreference = 'SilentlyContinue'
$out = 'E:\workbuddy\.wb_roaming2.txt'
$lines = New-Object System.Collections.Generic.List[string]
$skip = @('CodeBuddyExtension','WorkBuddy')

function Measure-Dir($path) {
    if (-not (Test-Path -LiteralPath $path)) { return -1 }
    try {
        $bytes = 0L
        $stack = New-Object System.Collections.Stack
        $stack.Push($path)
        while ($stack.Count -gt 0) {
            $dir = $stack.Pop()
            foreach ($f in [System.IO.Directory]::EnumerateFiles($dir, '*', [System.IO.SearchOption]::TopDirectoryOnly)) {
                try { $bytes += (Get-Item -LiteralPath $f -Force).Length } catch {}
            }
            foreach ($d in [System.IO.Directory]::EnumerateDirectories($dir, '*', [System.IO.SearchOption]::TopDirectoryOnly)) {
                $stack.Push($d)
            }
        }
        return $bytes
    } catch { return -2 }
}

$root = 'C:\Users\ASUS\AppData\Roaming'
$lines.Add("ROOT: $root")
$items = Get-ChildItem -LiteralPath $root -Force -Directory | Where-Object { $_.Name -notin $skip } | Sort-Object Name
$results = @()
foreach ($d in $items) {
    $sz = Measure-Dir $d.FullName
    if ($sz -ge 0) { $results += [PSCustomObject]@{ Name = $d.Name; MB = [math]::Round($sz/1MB,0) } }
}
$results | Sort-Object MB -Descending | ForEach-Object { $lines.Add(("{0,8} MB  {1}" -f $_.MB, $_.Name)) }
[System.IO.File]::WriteAllLines($out, $lines, [System.Text.Encoding]::UTF8)
Write-Output 'ROAMING2_DONE'
