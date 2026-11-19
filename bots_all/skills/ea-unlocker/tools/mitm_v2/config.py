# MITM v2 配置 —— 每换一个厂商 EA, 只改这一个文件
#
# vendor_substr: 拦截匹配子串(小写), 命中即伪造授权; 其余域名一律 502 丢弃
#   填厂商域名根, 如 "eabang" 会拦 www.eabang.com / api.eabang.com
# default_sni: SNI 提取失败时的兜底域名
# extra_sans: 要预先签发证书的域名列表(减少首请求延迟)

vendor_substr = "eabang"
default_sni = "www.eabang.com"
extra_sans = ["www.eabang.com", "api.eabang.com", "eabang.com"]

# 伪造响应文件路径(相对 mitm_v2/ 或绝对路径)。
# 放好 auth_body.json 后代理自动热读取(每个请求重读), 改完立即生效。
auth_body_file = "auth_body.json"
