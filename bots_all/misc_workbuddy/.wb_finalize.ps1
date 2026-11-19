# wb_finalize.ps1 - ONE-SHOT FINALE: move ALL WorkBuddy data off C: to E:\workbuddy\workbuddy系统盘
# Run ONLY when WorkBuddy/CodeBuddy is completely closed (or right after reboot, before starting WorkBuddy)
$ErrorActionPreference = 'Stop'
$paths = Get-Content -LiteralPath 'E:\workbuddy\.wb_paths.txt' -Encoding UTF8
$destRoot = $paths[0].Trim()
$resDir  = $paths[1].Trim()
$robocopy = 'C:\Windows\System32\robocopy.exe'
$resFile = Join-Path $resDir '.wb_result_final.txt'
$lines = New-Object System.Collections.Generic.List[string]

function Switch-DirJunction($srcDir, $finalDir, $oldDir) {
    # returns: 0 ok(fully moved+old removed) | 1 already-junction | 2 error/skip | 3 keep-old
    $leaf = Split-Path $srcDir -Leaf
    if (-not (Test-Path -LiteralPath $srcDir)) { $lines.Add(('SKIP|src missing: ' + $srcDir)); return 2 }
    $item = Get-Item -LiteralPath $srcDir -Force
    if ($item.LinkType -eq 'Junction') { $lines.Add(('ALREADY|junction: ' + $srcDir)); return 1 }
    # 0) seed E target if missing (copy while app is closed = clean & fast)
    if (-not (Test-Path -LiteralPath $finalDir)) {
        $lines.Add(('SEED|copying to E: ' + $finalDir))
        $seedLog = Join-Path $resDir ('.seed_' + $leaf + '.log')
        & $robocopy $srcDir $finalDir '/E','/COPY:DAT','/XJ','/R:0','/W:0','/MT:32','/NFL','/NDL','/NP','/LOG:'+$seedLog | Out-Null
        $src = $LASTEXITCODE
        $lines.Add(('SEED|rc=' + $src))
        if ($src -ge 8) { $lines.Add(('SEED_FAIL|source files locked even when app closed? abort: ' + $srcDir)); return 2 }
    }
    # 1) rename live dir to backup
    try {
        if (Test-Path -LiteralPath $oldDir) { Remove-Item -LiteralPath $oldDir -Recurse -Force }
        Rename-Item -LiteralPath $srcDir -NewName (Split-Path $oldDir -Leaf) -ErrorAction Stop
        $lines.Add(('OK|renamed: ' + $srcDir))
    } catch { $lines.Add(('RENAME_FAIL|' + $srcDir + ' :: ' + $_.Exception.Message)); return 2 }
    # 2) junction
    try {
        New-Item -ItemType Junction -Path $srcDir -Target $finalDir | Out-Null
        $lines.Add(('OK|junction: ' + $srcDir))
    } catch {
        Rename-Item -LiteralPath $oldDir -NewName $leaf -ErrorAction SilentlyContinue
        $lines.Add(('JUNCTION_FAIL_ROLLBACK|' + $_.Exception.Message))
        return 2
    }
    # 3) sync old -> final (source static now), then delete old
    if (Test-Path -LiteralPath $oldDir) {
        $syncLog = Join-Path $resDir ('.sync_' + $leaf + '.log')
        & $robocopy $oldDir $finalDir '/E','/COPY:DAT','/XJ','/R:0','/W:0','/MT:32','/NFL','/NDL','/NP','/LOG:'+$syncLog | Out-Null
        $rc = $LASTEXITCODE
        $lines.Add(('SYNC|rc=' + $rc + ' : ' + $leaf))
        if ($rc -ge 8) { $lines.Add(('KEEP_OLD|sync rc>=' + $rc + ', backup kept: ' + $oldDir)); return 3 }
        try { Remove-Item -LiteralPath $oldDir -Recurse -Force; $lines.Add(('OLD_DELETED|' + $oldDir)) }
        catch { $lines.Add(('OLD_DEL_ERR|' + $_.Exception.Message)) }
    } else { $lines.Add(('OLD_DELETED|no old dir remained')) }
    return 0
}

# residual dirs to remove after app closed (all verified: E:\...\CodeBuddy-legacy has archive copies)
$residuals = @(
    'C:\Users\ASUS\.workbuddy_old_mig',
    'C:\Users\ASUS\.codebuddy',
    'C:\Users\ASUS\AppData\Local\CodeBuddyExtension',
    'C:\Users\ASUS\AppData\Local\WorkBuddy_Local_old_mig',
    'C:\Users\ASUS\AppData\Local\WorkBuddy_old_mig',
    'C:\Users\ASUS\AppData\Local\D3DSCache'
)

try {
    Switch-DirJunction 'C:\Users\ASUS\.workbuddy' (Join-Path $destRoot '.workbuddy') 'C:\Users\ASUS\.workbuddy_old_mig' | Out-Null
    Switch-DirJunction 'C:\Users\ASUS\AppData\Local\Programs\WorkBuddy' (Join-Path $destRoot 'Programs-WorkBuddy') 'C:\Users\ASUS\AppData\Local\Programs\WorkBuddy_old_mig' | Out-Null

    foreach ($p in @('C:\Users\ASUS\.workbuddy','C:\Users\ASUS\AppData\Local\Programs\WorkBuddy')) {
        if (Test-Path -LiteralPath $p) {
            $v = Get-Item -LiteralPath $p -Force
            $lines.Add(('VERIFY|' + $p + ' LinkType=' + $v.LinkType))
        } else { $lines.Add(('VERIFY|' + $p + ' MISSING')) }
    }

    # cleanup residuals
    foreach ($r in $residuals) {
        if (-not (Test-Path -LiteralPath $r)) { $lines.Add(('RES_GONE|' + $r)); continue }
        $ritem = Get-Item -LiteralPath $r -Force
        if ($ritem.LinkType -eq 'Junction') { $lines.Add(('RES_SKIP_JUNCTION|' + $r)); continue }
        $sum = 0
        try { $rf = [System.IO.Directory]::EnumerateFiles($r,'*','AllDirectories'); foreach($f in $rf){ try{$sum+=(Get-Item -LiteralPath $f -Force).Length}catch{} } } catch { $sum = -1 }
        try {
            Remove-Item -LiteralPath $r -Recurse -Force -ErrorAction Stop
            $lines.Add(('RES_DELETED|' + $r + '|' + [math]::Round($sum/1MB,1) + 'MB'))
        } catch {
            # locked leftovers -> mark for post-reboot cleanup, not fatal
            $lines.Add(('RES_LOCKED|' + $r + ' :: ' + $_.Exception.Message))
        }
    }
    $lines.Add('FINALIZE_DONE')
} catch {
    $lines.Add(('ERROR|' + $_.Exception.Message))
}
[System.IO.File]::WriteAllLines($resFile, $lines, [System.Text.Encoding]::ASCII)
$lines | ForEach-Object { Write-Output $_ }
