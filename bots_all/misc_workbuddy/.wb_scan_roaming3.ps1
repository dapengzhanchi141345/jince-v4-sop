$out = 'E:\workbuddy\.wb_roaming3.txt'
$lines = New-Object System.Collections.Generic.List[string]
$root = 'C:\Users\ASUS\AppData\Roaming'
$dirs = Get-ChildItem -LiteralPath $root -Force -Directory | Select-Object -ExpandProperty Name
foreach ($n in $dirs) {
    $p = Join-Path $root $n
    $item = Get-Item -LiteralPath $p -Force
    if ($item.LinkType) { $lines.Add(("SKIPJUNC|{0}" -f $n)); continue }
    if ($n -in @('CodeBuddyExtension','Microsoft','Adobe','Macromedia')) { $lines.Add(("SKIP|{0}" -f $n)); continue }
    $bytes = 0L
    try {
        $res = cmd /c dir /a /s /-c "`"$p`"" 2>$null
        foreach ($ln in $res) {
            $m = [regex]::Match($ln, '([\d,]+)\s+[^\r\n]*?(?:个文件|File\(s\))\s+([\d,]+)\s+(?:字节|bytes)')
            if ($m.Success) { $bytes = [long]($m.Groups[2].Value -replace ',','') }
        }
    } catch {}
    $lines.Add(("{0,10} MB  {1}" -f [math]::Round($bytes/1MB,0), $n))
}
[System.IO.File]::WriteAllLines($out, $lines, [System.Text.Encoding]::UTF8)
Write-Output 'ROAMING3_DONE'
