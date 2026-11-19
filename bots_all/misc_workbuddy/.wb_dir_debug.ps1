$out = 'E:\workbuddy\.wb_dir_debug.txt'
$lines = New-Object System.Collections.Generic.List[string]
$p = 'C:\Users\ASUS\AppData\Roaming\QQ'
$res = cmd /c dir /a /s /-c "`"$p`"" 2>&1
$lines.Add(('LINES=' + $res.Count))
$lines.Add('--- LAST 15 ---')
for ($i = [Math]::Max(0, $res.Count - 15); $i -lt $res.Count; $i++) {
    $lines.Add(('[' + $i + '] ' + $res[$i]))
}
$lines.Add('--- BYTES-LIKE ---')
foreach ($ln in $res) {
    if ($ln -match '字节|bytes|File') { $lines.Add($ln) }
    if ($lines.Count -gt 60) { break }
}
[System.IO.File]::WriteAllLines($out, $lines, [System.Text.Encoding]::UTF8)
Write-Output 'DEBUG_DONE'
