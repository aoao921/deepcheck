inspec工具介绍
InSpec 是由 Chef 公司开发的开源基础设施安全与合规性测试框架，核心特点包括：
- 合规即代码（Compliance as Code）：通过编写可执行的测试代码来定义和验证系统的安全配置，例如将安全基准（如 CIS Benchmark）转化为可执行代码，确保一致性和可重复性。
- 无代理架构：无需在目标系统上安装代理，减少部署复杂性。
- 跨平台支持：InSpec 支持多种操作系统和环境，包括 Linux、Windows、macOS，以及容器和云平台（AWS/Azure/GCP）。
- 结果可视化：提供 CLI/HTML/JSON 等多种报告格式。
## 基础执行流程
inspec exec <PROFILE_PATH> \           # 指定测试套件
  -t ssh://user@host \                 # 指定目标（支持 local/docker/aws）
  --reporter json \  # 输出 JSON 形式
## 典型工作流：
1. 编写 Profile（包含 controls 测试用例）
2. 使用 `inspec check` 验证语法
3. 执行测试并获取机器可读报告
4. 解析报告进行风险分析