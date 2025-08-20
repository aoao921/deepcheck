```yaml
### Inspec 脚本能力清单
profiles:
  - id: 1
    name: windows_cis_benchmark
    desc: Windows安全基线检查
    logic: 根据CIS Microsoft Windows Server安全基线标准，检查Windows系统的安全配置合规性
    params:
      - name: host
        desc: 远程主机的ip地址或hostname
        required: false
      - name: user
        desc: 远程主机上的username
        required: false
      - name: password
        desc: 远程主机上的用户密码
        required: false
      - name: output_format
        desc: 输出格式(json或html)
        default: 'json'
        required: true
      - name: output_path
        default: 'output'
        desc: 输出文件路径
        required: true
      - name: script_path
        desc: Inspec 脚本路径
        default: 'profiles/windows-baseline'
        required: false

  - id: 2
    name: linux_baseline_check
    desc: Linux安全基线检查
    logic: 根据DevSec Linux安全基线标准，检查Linux系统的安全配置合规性
    params:
      - name: host
        desc: 远程主机的ip地址或hostname
        required: false
      - name: user
        desc: 远程主机上的username
        required: false
      - name: password
        desc: 远程主机上的用户密码
        required: false
      - name: output_format
        desc: 输出格式(json或html)
        default: 'json'
        required: true
      - name: output_path
        default: 'output'
        desc: 输出文件路径
        required: true
      - name: script_path
        desc: Inspec 脚本路径
        default: 'profiles/linux-baseline'
        required: false      

  - id: 3
    name: mysql_baseline_check
    desc: MySQL安全基线检查
    logic: 根据DevSec MySQL安全基线标准，检查MySQL数据库的安全配置合规性
    params:
      - name: host
        desc: 远程主机的ip地址或hostname
        required: false
      - name: user
        desc: 远程主机上的username
        required: false
      - name: password
        desc: 远程主机上的用户密码
        required: false
      - name: output_format
        desc: 输出格式(json或html)
        default: 'json'
        required: true
      - name: output_path
        desc: 输出文件路径
        required: true
      - name: script_path
        desc: Inspec 脚本路径
        default: 'profiles/mysql-baseline'
        required: false        

  - id: 4
    name: nginx_baseline_check
    desc: Nginx安全基线检查
    logic: 根据DevSec Nginx安全基线标准，检查Nginx Web服务器的安全配置合规性
    params:
      - name: host
        desc: 远程主机的ip地址或hostname
        required: false
      - name: user
        desc: 远程主机上的username
        required: false
      - name: password
        desc: 远程主机上的用户密码
        required: false
      - name: output_format
        desc: 输出格式(json或html)
        default: 'json'
        required: true
      - name: output_path
        desc: 输出文件路径
        required: true
      - name: script_path
        desc: Inspec 脚本路径
        default: 'profiles/nginx-baseline'
        required: false        

  - id: 5
    name: apache_baseline_check
    desc: Apache安全基线检查
    logic: 根据DevSec Apache安全基线标准，检查Apache Web服务器的安全配置合规性
    params:
      - name: host
        desc: 远程主机的ip地址或hostname
        required: false
      - name: user
        desc: 远程主机上的username
        required: false
      - name: password
        desc: 远程主机上的用户密码
        required: false
      - name: output_format
        desc: 输出格式(json或html)
        default: 'json'
        required: true
      - name: output_path
        desc: 输出文件路径
        required: true
      - name: script_path
        desc: Inspec 脚本路径
        default: 'profiles/apache-baseline'
        required: false        

  - id: 6
    name: tomcat_baseline_check
    desc: Tomcat安全基线检查
    logic: 根据Apache Tomcat安全基线标准，检查Tomcat应用服务器的安全配置合规性
    params:
      - name: host
        desc: 远程主机的ip地址或hostname
        required: false
      - name: user
        desc: 远程主机上的username
        required: false
      - name: password
        desc: 远程主机上的用户密码
        required: false
      - name: output_format
        desc: 输出格式(json或html)
        default: 'json'
        required: true
      - name: output_path
        desc: 输出文件路径
        required: true
      - name: script_path
        desc: Inspec 脚本路径
        default: 'profiles/tomcat-baseline'
        required: false        

  - id: 7
    name: docker_cis_benchmark
    desc: Docker CIS基准检查
    logic: 根据CIS Docker基准标准，检查Docker环境的安全配置合规性
    params:
      - name: host
        desc: 远程主机的ip地址或hostname
        required: false
      - name: user
        desc: 远程主机上的username
        required: false
      - name: password
        desc: 远程主机上的用户密码
        required: false
      - name: output_format
        desc: 输出格式(json或html)
        default: 'json'
        required: true
      - name: output_path
        default: 'output'
        desc: 输出文件路径
        required: true
      - name: script_path
        desc: Inspec 脚本路径
        default: 'profiles/cis-docker-benchmark'
        required: false        
```
