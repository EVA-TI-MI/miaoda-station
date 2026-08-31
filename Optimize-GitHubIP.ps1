<#
.SYNOPSIS
    GitHub IP 优选 / 重测脚本（Windows PowerShell 5.1+ 兼容，无第三方依赖）

.DESCRIPTION
    每次运行都重新：拉取 GitHub 官方网段(api.github.com/meta) -> 采样候选 IP ->
    异步并发实测 TCP 443 握手延迟 -> 对最快 IP 做 TLS+HTTP 真连校验 -> 排序输出。
    加 -Apply 会把最优结果幂等写入 hosts（带标记块，可反复“重测”覆盖；默认只测不改，安全）。

    相比网上常见脚本的改进：
      1. 候选 IP 来自 GitHub 官方 /meta 权威网段（拉不到才用内置兜底），不写死、不爬第三方 IP 站；
      2. 不只 ping（ICMP 常被禁且不代表 443 可用），以 TCP 443 握手延迟为准，并做 TLS+HTTP 校验；
      3. 全异步并发，数百候选 IP 也能在几十秒内测完；
      4. hosts 用标记块幂等更新并自动备份，重复运行不会堆叠重复行；
      5. 默认只读测试，绝不擅自改系统；显式 -Apply 且为管理员才写 hosts。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\Optimize-GitHubIP.ps1
    # 只测速并打印每个域名的最优 IP，不改系统

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\Optimize-GitHubIP.ps1 -Apply
    # 测速并把最优 IP 写入 hosts（需要“以管理员身份运行”）

.EXAMPLE
    .\Optimize-GitHubIP.ps1 -TimeoutMs 1200 -PerSubnet 8 -Top 3 -OutFile result.csv
#>
[CmdletBinding()]
param(
    # 每个 CIDR 网段均匀采样的候选 IP 数（越大越全、越慢）
    [int]$PerSubnet = 6,
    # TCP 连接超时(毫秒)
    [int]$TimeoutMs = 1500,
    # 每个 IP 重复测量次数，取最优（最小延迟）
    [int]$Tries = 2,
    # 每个域名最终保留前 N 个最优 IP
    [int]$Top = 3,
    # 候选总数上限（防止网段过多时爆炸）
    [int]$MaxCandidates = 600,
    # 并发批次大小
    [int]$BatchSize = 64,
    # 是否对最快 IP 做 TLS+HTTP 真连校验（更准，略慢）
    [switch]$NoHttpVerify,
    # TLS+HTTP 校验超时(毫秒)，跨境握手比 TCP 慢，单独给足
    [int]$VerifyTimeoutMs = 5000,
    # 进入 TLS+HTTP 校验的候选数量（在 TCP 最快的若干个里挑）
    [int]$VerifyPool = 40,
    # 写入 hosts（默认只测不改）
    [switch]$Apply,
    # 导出 CSV 路径（可选）
    [string]$OutFile,
    # 强制使用内置兜底网段，跳过在线获取 /meta
    [switch]$Offline
)

$ErrorActionPreference = 'Stop'
function Write-Step($m){ Write-Host "[*] $m" -ForegroundColor Cyan }
function Write-Ok($m){ Write-Host "[v] $m" -ForegroundColor Green }
function Write-Warn2($m){ Write-Host "[!] $m" -ForegroundColor Yellow }

# ---------- 1. 目标域名 -> 用 /meta 的哪些网段分组 ----------
# Core 组：github.com / api / codeload（git+api 段）
# Edge 组：githubusercontent（raw/objects/release-assets）与 github.io Pages（web+pages 段）
$DomainGroups = [ordered]@{
    'Core' = @('github.com','api.github.com','codeload.github.com')
    'Edge' = @('raw.githubusercontent.com','objects.githubusercontent.com',
               'release-assets.githubusercontent.com','eva-ti-mi.github.io')
}
# 内置兜底网段（/meta 拉取失败时使用；均为 GitHub 公开网段）
$FallbackCidrs = @{
    'Core' = @('140.82.112.0/20','192.30.252.0/22','140.82.121.0/24')
    'Edge' = @('185.199.108.0/22','185.199.108.0/24','185.199.109.0/24','185.199.110.0/24','185.199.111.0/24')
}

# ---------- 2. CIDR -> 均匀采样 IP ----------
function Convert-IpToUInt32([string]$ip){
    $b=[System.Net.IPAddress]::Parse($ip).GetAddressBytes();[Array]::Reverse($b)
    return [BitConverter]::ToUInt32($b,0)
}
function Convert-UInt32ToIp([uint32]$n){
    $b=[BitConverter]::GetBytes($n);[Array]::Reverse($b)
    return [System.Net.IPAddress]::new($b)
}
function Expand-Cidr([string]$cidr,[int]$sample){
    if($cidr -match ':'){ return }  # 跳过 IPv6 网段，仅处理 IPv4
    $parts=$cidr.Split('/')
    $start=Convert-IpToUInt32 $parts[0]
    $prefix=[int]$parts[1]
    $size=[uint32]([Math]::Pow(2,32-$prefix))
    $end=$start+$size-1
    if($size -le $sample){
        for($u=$start;$u -le $end;$u++){ Convert-UInt32ToIp $u | ForEach-Object { $_.ToString() } }
    } else {
        # 均匀采样 sample 个点（含首尾）
        for($i=0;$i -lt $sample;$i++){
            $off=[uint32]([Math]::Floor(($size-1)*$i/[double]([Math]::Max(1,$sample-1))))
            (Convert-UInt32ToIp ($start+$off)).ToString()
        }
    }
}

# ---------- 3. 获取候选 IP ----------
function Get-Candidates{
    $groupCidrs=@{}
    if($Offline){
        Write-Warn2 "离线模式，使用内置兜底网段"
        $groupCidrs=$FallbackCidrs
    } else {
        try{
            Write-Step "拉取 GitHub 官方网段 api.github.com/meta ..."
            $meta=Invoke-RestMethod 'https://api.github.com/meta' -Headers @{'User-Agent'='GitHubIP-Optimizer'} -TimeoutSec 30
            $groupCidrs=@{
                'Core' = @($meta.git + $meta.api | Select-Object -Unique)
                'Edge' = @($meta.web + $meta.pages | Select-Object -Unique)
            }
            Write-Ok "官方网段：Core $($groupCidrs.Core.Count) 段 / Edge $($groupCidrs.Edge.Count) 段"
        }catch{
            Write-Warn2 "官方网段拉取失败($($_.Exception.Message))，改用内置兜底网段"
            $groupCidrs=$FallbackCidrs
        }
    }
    $result=@{}
    foreach($g in $groupCidrs.Keys){
        $set=New-Object 'System.Collections.Generic.HashSet[string]'
        foreach($c in $groupCidrs[$g]){
            foreach($ip in (Expand-Cidr $c $PerSubnet)){ [void]$set.Add($ip) }
        }
        $list=@($set)
        if($list.Count -gt $MaxCandidates){ # 过多则随机抽样到上限
            $rng=[System.Random]::new(); $list=$list | Sort-Object { $rng.Next() } | Select-Object -First $MaxCandidates
        }
        $result[$g]=$list
    }
    return $result
}

# ---------- 4. 异步并发 TCP 443 测速 ----------
# 单批真异步并发探测：所有 IP 同时发起 ConnectAsync，主线程轮询任务状态记录握手耗时
# （不在 ContinueWith 里跑 PS 脚本块——那会跨 runspace 线程被静默吞掉）
function Invoke-AsyncProbe([string[]]$ips,[int]$timeoutMs){
    $items=New-Object System.Collections.ArrayList
    foreach($ip in $ips){
        try{
            $addr=[System.Net.IPAddress]::Parse($ip)
            if($addr.AddressFamily -ne 'InterNetwork'){ continue }  # 仅 IPv4
            $c=New-Object System.Net.Sockets.TcpClient
            $sw=[System.Diagnostics.Stopwatch]::StartNew()
            $task=$c.ConnectAsync($ip,443)
            [void]$items.Add([pscustomobject]@{Ip=$ip;Client=$c;Task=$task;Sw=$sw;Done=$false;Ms=$null})
        }catch{ continue }
    }
    $overall=[System.Diagnostics.Stopwatch]::StartNew()
    $pending=$items.Count
    while($pending -gt 0 -and $overall.ElapsedMilliseconds -lt ($timeoutMs+1500)){
        foreach($it in $items){
            if($it.Done){continue}
            if($it.Task.IsCompleted){
                $it.Done=$true;$pending--;$it.Sw.Stop()
                if($it.Task.Status -eq 'RanToCompletion' -and $it.Client.Connected){ $it.Ms=[int]$it.Sw.ElapsedMilliseconds }
            }
        }
        if($pending -gt 0){ Start-Sleep -Milliseconds 5 }
    }
    $out=New-Object System.Collections.ArrayList
    foreach($it in $items){
        try{ if($it.Client){$it.Client.Dispose()} }catch{}
        if($null -ne $it.Ms){ [void]$out.Add([pscustomobject]@{Key=$it.Ip;Value=$it.Ms}) }
    }
    return $out.ToArray()
}
function Measure-Candidates([string[]]$ips){
    $n=$ips.Count; Write-Step "实测 TCP 443：$n 个候选 IP，异步并发、重复 $Tries 轮取最优 ..."
    $best=@{}
    for($round=1;$round -le $Tries;$round++){
        for($s=0;$s -lt $n;$s+=$BatchSize){
            $batch=$ips[$s..([Math]::Min($s+$BatchSize-1,$n-1))]
            $r=Invoke-AsyncProbe $batch $TimeoutMs
            foreach($kv in $r){
                if(-not $best.ContainsKey($kv.Key) -or $kv.Value -lt $best[$kv.Key]){ $best[$kv.Key]=$kv.Value }
            }
            Write-Progress -Activity "GitHub IP 测速(第 $round/$Tries 轮)" -Status "$([Math]::Min($s+$BatchSize,$n)) / $n" -PercentComplete ([int](100*($s+$batch.Count)/$n))
        }
    }
    Write-Progress -Activity 'GitHub IP 测速' -Completed
    $rows=@();foreach($k in $best.Keys){$rows+=[pscustomobject]@{Ip=$k;LatencyMs=$best[$k]}}
    return @($rows | Sort-Object LatencyMs)
}

# ---------- 5. 对最快 IP 做 TLS+HTTP 真连校验 ----------
# 逐步严格判定：TCP 连上 -> TLS(默认证书校验,正确 SNI) 握手成功 -> 读到 HTTP 状态行。
# 用系统默认证书校验（不用 PS 脚本块当证书回调——跨委托会失败）；
# 任意 HTTP 状态码(200/301/404...)都算“该 IP 能正常承载此站点 TLS”，重点是没被 SNI 阻断。
function Test-HttpOverTls([string]$ip,[string]$hostName,[int]$timeoutMs){
    $tcp=$null;$ssl=$null
    try{
        $tcp=New-Object System.Net.Sockets.TcpClient
        $ct=$tcp.ConnectAsync($ip,443)
        if(-not $ct.Wait($timeoutMs)){return $false}
        if(-not $tcp.Connected){return $false}

        $ssl=New-Object System.Net.Security.SslStream($tcp.GetStream(),$false)
        $at=$ssl.AuthenticateAsClientAsync($hostName)
        if(-not $at.Wait($timeoutMs)){return $false}
        if($at.IsFaulted -or -not $ssl.IsAuthenticated){return $false}

        $req="HEAD / HTTP/1.1`r`nHost: $hostName`r`nConnection: close`r`nUser-Agent: GitHubIP-Optimizer`r`n`r`n"
        $bytes=[Text.Encoding]::ASCII.GetBytes($req)
        $ssl.Write($bytes,0,$bytes.Length)
        $buf=New-Object byte[] 128
        $rt=$ssl.ReadAsync($buf,0,128)
        if(-not $rt.Wait($timeoutMs)){return $false}
        $read=$rt.Result
        if($read -le 0){return $false}
        $head=[Text.Encoding]::ASCII.GetString($buf,0,$read)
        return [bool]($head -match 'HTTP/1\.[01]\s+\d{3}')
    }catch{return $false}
    finally{
        if($ssl){try{$ssl.Dispose()}catch{}}
        if($tcp){try{$tcp.Dispose()}catch{}}
    }
}

# ---------- 主流程 ----------
Write-Host "===== GitHub IP 优选 / 重测  $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') =====" -ForegroundColor White
$cands=Get-Candidates
$picked=[ordered]@{}
$allRows=@()
foreach($g in $DomainGroups.Keys){
    Write-Host "`n===== 分组 $g =====" -ForegroundColor White
    $ranked=Measure-Candidates $cands[$g]
    Write-Ok "$g 组可用 IP：$($ranked.Count) 个"
    $final=@()
    if($NoHttpVerify){
        $final=@($ranked | Select-Object -First $Top)
    } else {
        $probeHost=$DomainGroups[$g][0]
        $pool=$ranked | Select-Object -First ([Math]::Min($VerifyPool,$ranked.Count))
        Write-Step "对 TCP 最快的 $($pool.Count) 个 IP 做 TLS+HTTP 校验(SNI=$probeHost, 超时${VerifyTimeoutMs}ms) ..."
        foreach($r in $pool){
            if($final.Count -ge $Top){break}
            $ok=Test-HttpOverTls $r.Ip $probeHost $VerifyTimeoutMs
            if($ok){ $final+=$r }
        }
    }
    $picked[$g]=$final
    foreach($r in $final){
        Write-Host ("  {0,-16} {1,5} ms" -f $r.Ip,$r.LatencyMs) -ForegroundColor Green
        foreach($d in $DomainGroups[$g]){ $allRows += [pscustomobject]@{Group=$g;Domain=$d;Ip=$r.Ip;LatencyMs=$r.LatencyMs} }
    }
    if($final.Count -eq 0){ Write-Warn2 "$g 组没有通过校验的 IP，可增大 -TimeoutMs 或稍后重试" }
}

# ---------- 汇总 ----------
$mapping=@()
foreach($g in $picked.Keys){
    $ips=@($picked[$g]|ForEach-Object{$_.Ip})
    foreach($d in $DomainGroups[$g]){ $mapping += [pscustomobject]@{Domain=$d;IPs=($ips -join ', ')} }
}
Write-Host "`n===== 推荐 hosts 映射 =====" -ForegroundColor White
$mapping | Format-Table -AutoSize | Out-String | Write-Host
if($OutFile){ $allRows | Export-Csv -Path $OutFile -NoTypeInformation -Encoding UTF8; Write-Ok "明细已导出: $OutFile" }

# ---------- 写 hosts（仅 -Apply） ----------
if($Apply){
    $hostsPath="$env:windir\System32\drivers\etc\hosts"
    $isAdmin=([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)
    if(-not $isAdmin){ Write-Warn2 "写 hosts 需要管理员权限：请用“以管理员身份运行”的 PowerShell 再加 -Apply 执行"; exit 1 }
    if(-not (Test-Path $hostsPath)){ Write-Warn2 "未找到 hosts: $hostsPath"; exit 1 }
    $lines=[System.Collections.Generic.List[string]](Get-Content $hostsPath)
    $begin='# >>> GitHubIP-Optimizer BEGIN >>>';$end='# <<< GitHubIP-Optimizer END <<<'
    # 删除旧块（幂等）
    $bi=$lines.IndexOf($begin)
    if($bi -ge 0){
        $ei=$lines.IndexOf($end)
        if($ei -ge $bi){ $lines.RemoveRange($bi,$ei-$bi+1) }
    }
    Copy-Item $hostsPath ("{0}.bak_{1}" -f $hostsPath,(Get-Date -Format 'yyyyMMddHHmmss')) -Force
    $block=New-Object System.Collections.Generic.List[string]
    $block.Add($begin);$block.Add("# updated $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') by Optimize-GitHubIP.ps1")
    foreach($m in $mapping){ foreach($ip in ($m.IPs -split ', ')){ if($ip){$block.Add(("$ip  $($m.Domain)"))} } }
    $block.Add($end)
    if($lines.Count -gt 0 -and $lines[$lines.Count-1].Trim() -ne ''){$lines.Add('')}
    $lines.AddRange($block)
    [IO.File]::WriteAllLines($hostsPath,$lines,(New-Object Text.UTF8Encoding($false)))
    Write-Ok "hosts 已更新（已自动备份）：$hostsPath"
    Write-Step "执行 ipconfig /flushdns 刷新 DNS ..."
    ipconfig /flushdns | Out-Null
    Write-Ok "完成"
}else{
    Write-Host "`n当前为只测模式，未修改系统。确认结果无误后，以管理员身份加 -Apply 写入 hosts。" -ForegroundColor Yellow
}
