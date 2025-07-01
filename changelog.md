# Changelog

## 2023-11-10

### 功能增强
- 在 InspecClient 中添加了对 SSH 密码认证的支持
  - 修改了 `inspec_client.py` 中的 `_build_inspec_command` 方法，支持使用用户名和密码进行 SSH 连接
  - 更新了 `background_inspec_scripts.md` 中所有脚本配置，添加了 password 参数字段
  - 命令格式更新为: `inspec exec <script_path> -t ssh://<user>:<password>@<host>`
- 在 Warroom 界面中添加了可视化按钮
  - 在控制区域添加了跳转到 `/test` 可视化页面的按钮
  - 使用新标签页打开，不影响当前操作